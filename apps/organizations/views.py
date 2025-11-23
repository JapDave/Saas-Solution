from __future__ import annotations

from django.http import Http404
from django.db.models import Q
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.common.exceptions import (
    CustomError,
    ORGANIZATION_CREATION_FAILED,
    ORGANIZATION_UPDATE_FAILED,
)
from apps.accounts.services import get_assigned_account_ids
from apps.roles.permissions import OrganizationPermission
from apps.roles.serializers import RoleAssignmentSerializer
from apps.roles.services import assign_organization_owner, transfer_organization_owner
from apps.roles.utils import has_role
from apps.roles.constants import (
    ROLE_ORGANIZATION_OWNER,
)
from apps.subscriptions.services import ensure_organization_has_no_active_subscriptions

from .models import Organization
from .serializers import (
    OrganizationCreateSerializer,
    OrganizationUpdateSerializer,
    OrganizationReadSerializer,
    OrganizationOwnerAssignSerializer,
    OrganizationOwnerTransferSerializer,
)


class OrganizationViewSet(viewsets.ModelViewSet):
    """
    Views = pure logic; validation in serializers.

    Permissions (OrganizationPermission):
      - Superadmin: full access
      - Staff: CRUD only for organizations under accounts assigned to them
      - Account owners/admins: list + CRUD for organizations inside their own accounts
    """
    permission_classes = [OrganizationPermission]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "updated_at", "name"]
    filterset_fields = ["account", "is_active"]

    # Use UUID for detail routes: /api/organizations/<uuid>/
    lookup_field = "uuid"

    def get_queryset(self):
        qs = Organization.objects.select_related("account").order_by("-created_at")
        user = getattr(self.request, "user", None)
        if not (user and user.is_authenticated):
            return qs.none()

        if user.is_superuser:
            return qs

        if user.is_staff:
            assigned = get_assigned_account_ids(user)
            if not assigned:
                return qs.none()
            return qs.filter(account_id__in=assigned)

        return qs.filter(
            Q(created_by_id=user.id) |
            Q(account__created_by_id=user.id) |
            Q(memberships__user_id=user.id, memberships__deleted_at__isnull=True)
        ).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return OrganizationCreateSerializer
        if self.action in ("update", "partial_update"):
            return OrganizationUpdateSerializer
        return OrganizationReadSerializer

    # CREATE -> respond with read shape
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
        except Exception as exc:
            from apps.common.exceptions import CustomError, ORGANIZATION_NAME_EXISTS, INVALID_ORGANIZATION_DATA
            if isinstance(exc, CustomError):
                code = getattr(exc, "detail", {}).get("code")
                if code == ORGANIZATION_NAME_EXISTS:
                    # Remap to INVALID for views as per tests
                    raise CustomError(
                        code=INVALID_ORGANIZATION_DATA,
                        status_code=409,
                        detail="Organization name already exists in the account",
                    ) from exc
            raise
        try:
            obj = ser.save(created_by=request.user, updated_by=request.user)
        except Exception as exc:
            raise CustomError(
                code=ORGANIZATION_CREATION_FAILED,
                status_code=400,
                detail="Organization creation process failed",
            ) from exc
        try:
            assign_organization_owner(
                organization=obj,
                user=request.user,
                assigned_by=request.user,
            )
        except Exception as exc:
            raise ValidationError({'detail': f'Failed to assign organization owner: {exc}'}) from exc
        return Response(OrganizationReadSerializer(obj).data, status=status.HTTP_201_CREATED)

    # UPDATE/PATCH -> respond with read shape
    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, *, partial: bool):
        obj = self.get_object()  # Http404 mapped by handler to ORGANIZATION_NOT_FOUND

        ser = self.get_serializer(obj, data=request.data, partial=partial)
        try:
            ser.is_valid(raise_exception=True)
        except Exception as exc:
            from apps.common.exceptions import CustomError, ORGANIZATION_NAME_EXISTS, INVALID_ORGANIZATION_DATA
            if isinstance(exc, CustomError):
                code = getattr(exc, "detail", {}).get("code")
                if code == ORGANIZATION_NAME_EXISTS:
                    raise CustomError(
                        code=INVALID_ORGANIZATION_DATA,
                        status_code=400,
                        detail="Organization name already exists in the account",
                    ) from exc
            raise
        try:
            obj = ser.save(updated_by=request.user)
        except Exception as exc:
            raise CustomError(
                code=ORGANIZATION_UPDATE_FAILED,
                status_code=400,
                detail="Organization update process failed",
            ) from exc
        return Response(OrganizationReadSerializer(obj).data, status=status.HTTP_200_OK)

    # DELETE (soft)
    def destroy(self, request, *args, **kwargs):
        obj = self.get_object()  # respects lookup_field=uuid and scoped queryset

        ensure_organization_has_no_active_subscriptions(obj)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


    @action(detail=True, methods=["post"], url_path="assign-owner")
    def assign_owner(self, request, uuid=None):
        organization = self.get_object()
        serializer = OrganizationOwnerAssignSerializer(
            data=request.data,
            context={"organization": organization},
        )
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            detail = getattr(exc, "detail", exc.args)
            if isinstance(detail, dict) and "user" in detail:
                return Response({"user": detail["user"]}, status=status.HTTP_400_BAD_REQUEST)
            raise
        user = serializer.validated_data["user"]
        try:
            assignment = assign_organization_owner(
                organization=organization,
                user=user,
                assigned_by=request.user,
            )
        except Exception as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        read = RoleAssignmentSerializer(
            assignment,
            context={"request": request},
        )
        return Response(read.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="transfer-owner")
    def transfer_owner(self, request, uuid=None):
        organization = self.get_object()
        serializer = OrganizationOwnerTransferSerializer(
            data=request.data,
            context={"organization": organization},
        )
        serializer.is_valid(raise_exception=True)
        new_owner = serializer.validated_data["new_owner"]
        current_owner = serializer.validated_data.get("current_owner") or request.user

        # Only an existing organization owner may transfer ownership.
        if not has_role(request.user, ROLE_ORGANIZATION_OWNER, str(organization.uuid)):
            raise PermissionDenied("Only organization owners may transfer ownership.")

        try:
            assignment = transfer_organization_owner(
                organization=organization,
                new_owner=new_owner,
                assigned_by=request.user,
                current_owner=current_owner,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        read = RoleAssignmentSerializer(
            assignment,
            context={"request": request},
        )
        return Response(read.data, status=status.HTTP_200_OK)
