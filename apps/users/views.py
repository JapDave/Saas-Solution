from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import (
    InsufficientPermissions,
    CustomError,
    CustomValidationError,
    INVALID_USER_DATA,
    USER_CREATION_FAILED,
    USER_UPDATE_FAILED,
)
from apps.common.models import AuditLog
from apps.roles.models import RoleAssignment

from .models import UserOrganization
from .serializers import (
    MembershipMutationSerializer,
    MembershipRemovalSerializer,
    MembershipSerializer,
    UserCreateSerializer,
    UserReadSerializer,
    UserStatusUpdateSerializer,
    UserUpdateSerializer,
)
from .services import (
    get_user_accessible_account_ids,
    get_user_accessible_organization_ids,
    ensure_user_can_manage_user,
    ensure_user_not_owner_for_deactivate,
    ensure_user_not_owner_for_delete,
)

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """User lifecycle management across organizations."""

    def _log_user_event(
        self,
        *,
        request,
        view_name: str,
        model: str,
        action: str,
        object_id: str | None,
        status_code: int,
        extra: dict | None = None,
    ) -> None:
        AuditLog.objects.create(
            user=request.user,
            method=request.method,
            path=request.path,
            view=view_name,
            app_label="users",
            model=model,
            action=action,
            object_id=str(object_id or ""),
            status_code=status_code,
            success=200 <= status_code < 400,
            extra=extra or {},
        )

    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def get_throttle_scope(self, request):
        action = getattr(self, "action", None)
        if action == "add_membership":
            return "user.membership_add"
        if action == "remove_membership":
            return "user.membership_remove"
        if action == "switch_organization":
            return "user.session_switch"
        if action == "create":
            return "user.create"
        if action in {"partial_update", "status_change"}:
            return "user.update"
        if action == "list":
            return "user.list"
        return None

    def get_queryset(self):
        user = getattr(self.request, "user", None)
        qs = (
            User.objects.select_related("created_by", "updated_by")
            .prefetch_related("memberships__organization__account")
            .order_by("-created_at")
        )
        if not (user and user.is_authenticated):
            return qs.none()
        if user.is_superuser:
            return qs
        account_ids = get_user_accessible_account_ids(user)
        organization_ids = get_user_accessible_organization_ids(user)
        filters = Q(id=user.id)
        if account_ids:
            filters |= Q(memberships__organization__account_id__in=account_ids)
        if organization_ids:
            filters |= Q(memberships__organization_id__in=organization_ids)
        return qs.filter(filters).distinct()

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in {"update", "partial_update"}:
            return UserUpdateSerializer
        if self.action == "status_change":
            return UserStatusUpdateSerializer
        if self.action == "add_membership":
            return MembershipMutationSerializer
        if self.action == "remove_membership":
            return MembershipRemovalSerializer
        return UserReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except Exception as exc:
            raise CustomError(
                code=USER_CREATION_FAILED,
                status_code=400,
                detail="User creation process failed",
            ) from exc
        after_memberships = [
            self._capture_membership_state(user, membership.organization)
            for membership in user.memberships.all()
        ]
        read = UserReadSerializer(user, context={"request": request})
        self._log_user_event(
            request=request,
            view_name="UserViewSet.create",
            model="User",
            action="create",
            object_id=str(user.uuid),
            status_code=status.HTTP_201_CREATED,
            extra={"memberships_before": [], "memberships_after": after_memberships},
        )
        return Response(read.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        request_user = request.user
        allow_self = request_user.id == target.id
        ensure_user_can_manage_user(
            request_user,
            target,
            require_permission="user:update",
            allow_self=allow_self,
        )
        serializer = self.get_serializer(
            target, data=request.data, partial=True, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        read = UserReadSerializer(user, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        raise InvalidUserData(detail="Full updates are not supported. Use PATCH.")

    def destroy(self, request, *args, **kwargs):
        target = self.get_object()
        ensure_user_not_owner_for_delete(target)
        ensure_user_can_manage_user(
            request.user, target, require_permission="user:delete"
        )
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="status")
    def status_change(self, request, uuid=None):
        target = self.get_object()
        serializer = UserStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_active = serializer.validated_data["is_active"]
        request_user = request.user
        ensure_user_can_manage_user(
            request_user, target, require_permission="user:deactivate", allow_self=False
        )
        if not is_active:
            ensure_user_not_owner_for_deactivate(target)
        with transaction.atomic():
            previous_state = target.is_active
            target.is_active = is_active
            target.updated_by = request_user
            target.save(update_fields=["is_active", "updated_by", "updated_at"])
            self._log_user_event(
                request=request,
                view_name="UserViewSet.status_change",
                model="User",
                action="status_change",
                object_id=str(target.id),
                status_code=status.HTTP_200_OK,
                extra={"from": previous_state, "to": is_active},
            )
        read = UserReadSerializer(target, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="memberships")
    def add_membership(self, request, uuid=None):
        target = self.get_object()
        ensure_user_can_manage_user(
            request.user, target, require_permission="user:manage_membership"
        )
        serializer = MembershipMutationSerializer(
            data=request.data,
            context={"request": request, "user": target},
        )
        serializer.is_valid(raise_exception=True)
        organization = serializer.validated_data["organization"]
        before_state = self._capture_membership_state(target, organization)
        membership = serializer.save()
        after_state = self._capture_membership_state(target, organization)
        read = MembershipSerializer(membership, context={"request": request})
        response = Response(read.data, status=status.HTTP_201_CREATED)
        self._log_user_event(
            request=request,
            view_name="UserViewSet.add_membership",
            model="UserOrganization",
            action="membership_add",
            object_id=str(membership.uuid),
            status_code=status.HTTP_201_CREATED,
            extra={
                "target_user": str(target.uuid),
                "organization_uuid": str(membership.organization.uuid),
                "before": before_state,
                "after": after_state,
            },
        )
        return response

    @action(
        detail=True,
        methods=["delete"],
        url_path="memberships/(?P<organization_id>[^/]+)",
    )
    def remove_membership(self, request, uuid=None, organization_id=None):
        target = self.get_object()
        ensure_user_can_manage_user(
            request.user, target, require_permission="user:manage_membership"
        )
        serializer = MembershipRemovalSerializer(
            data={"organization": organization_id},
            context={"request": request, "user": target},
        )
        serializer.is_valid(raise_exception=True)
        organization = serializer.validated_data["organization"]
        before_state = self._capture_membership_state(target, organization)
        serializer.remove()
        after_state = self._capture_membership_state(target, organization)
        self._log_user_event(
            request=request,
            view_name="UserViewSet.remove_membership",
            model="UserOrganization",
            action="membership_remove",
            object_id=str(before_state.get("membership_uuid") or organization_id or ""),
            status_code=status.HTTP_204_NO_CONTENT,
            extra={
                "target_user": str(target.uuid),
                "organization_uuid": str(
                    getattr(organization, "uuid", organization_id)
                ),
                "before": before_state,
                "after": after_state,
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="switch-organization")
    def switch_organization(self, request):
        organization_uuid = request.data.get("organization_uuid")
        if not organization_uuid:
            raise CustomValidationError(
                detail="Organization UUID is required.", code=INVALID_USER_DATA
            )
        try:
            membership = UserOrganization.objects.get(
                user=request.user, organization__uuid=organization_uuid
            )
        except UserOrganization.DoesNotExist as exc:
            raise InsufficientPermissions() from exc
        if not membership.is_active or membership.deleted_at is not None:
            raise InsufficientPermissions()
        has_active_role = RoleAssignment.objects.filter(
            user=request.user,
            organization_id=membership.organization_id,
            is_active=True,
            deleted_at__isnull=True,
        ).exists()
        if not has_active_role:
            raise InsufficientPermissions()
        request.session["active_organization_id"] = membership.organization_id
        return Response(
            {"organization_uuid": str(membership.organization.uuid)}, status=status.HTTP_200_OK
        )

    def _capture_membership_state(self, user, organization) -> dict:
        membership = UserOrganization.objects.filter(
            user=user,
            organization=organization,
            deleted_at__isnull=True,
            is_active=True,
        ).first()
        assignments = (
            RoleAssignment.objects.filter(
                user=user,
                organization=organization,
                deleted_at__isnull=True,
                is_active=True,
            )
            .select_related("role")
            .order_by("role__name")
        )
        return {
            "membership_exists": membership is not None,
            "membership_uuid": str(membership.uuid) if membership else None,
            "permissions": list(membership.permission_keys if membership else []),
            "roles": [
                {"uuid": str(assignment.role.uuid), "name": assignment.role.name}
                for assignment in assignments
            ],
        }

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        read = UserReadSerializer(user, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserReadSerializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)
        serializer = UserReadSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, *, partial: bool):
        obj = self.get_object()
        serializer = self.get_serializer(obj, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except Exception as exc:
            raise CustomError(
                code=USER_UPDATE_FAILED,
                status_code=400,
                detail="User update process failed",
            ) from exc
        read = UserReadSerializer(user, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    # Use default get_object; Http404 is mapped by handler to USER_NOT_FOUND via domain
