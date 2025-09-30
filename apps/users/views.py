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
    InvalidUserData,
    UserNotFound,
)
from apps.common.models import AuditLog
from apps.common.paginations import StandardPagination

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
    actor_accessible_account_ids,
    actor_accessible_organization_ids,
    assert_actor_can_manage_user,
    ensure_user_not_owner_for_deactivate,
    ensure_user_not_owner_for_delete,
)

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """User lifecycle management across organizations."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

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
        account_ids = actor_accessible_account_ids(user)
        organization_ids = actor_accessible_organization_ids(user)
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
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        read = UserReadSerializer(user, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        target = self.get_object()
        actor = request.user
        allow_self = actor.id == target.id
        assert_actor_can_manage_user(actor, target, require_permission="user:update", allow_self=allow_self)
        serializer = self.get_serializer(target, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        read = UserReadSerializer(user, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        raise InvalidUserData(detail="Full updates are not supported. Use PATCH.")

    def destroy(self, request, *args, **kwargs):
        target = self.get_object()
        ensure_user_not_owner_for_delete(target)
        assert_actor_can_manage_user(request.user, target, require_permission="user:delete")
        target.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="status")
    def status_change(self, request, uuid=None):
        target = self.get_object()
        serializer = UserStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        is_active = serializer.validated_data["is_active"]
        actor = request.user
        assert_actor_can_manage_user(actor, target, require_permission="user:deactivate", allow_self=False)
        if not is_active:
            ensure_user_not_owner_for_deactivate(target)
        with transaction.atomic():
            previous_state = target.is_active
            target.is_active = is_active
            target.updated_by = actor
            target.save(update_fields=["is_active", "updated_by", "updated_at"])
            AuditLog.objects.create(
                user=actor,
                method=request.method,
                path=request.path,
                view="UserViewSet.status_change",
                app_label="users",
                model="User",
                action="status_change",
                object_id=str(target.id),
                status_code=status.HTTP_200_OK,
                success=True,
                extra={"from": previous_state, "to": is_active},
            )
        read = UserReadSerializer(target, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="memberships")
    def add_membership(self, request, uuid=None):
        target = self.get_object()
        assert_actor_can_manage_user(request.user, target, require_permission="user:manage_membership")
        serializer = MembershipMutationSerializer(
            data=request.data,
            context={"request": request, "user": target},
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        read = MembershipSerializer(membership, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path="memberships/(?P<organization_id>[^/]+)")
    def remove_membership(self, request, uuid=None, organization_id=None):
        target = self.get_object()
        assert_actor_can_manage_user(request.user, target, require_permission="user:manage_membership")
        serializer = MembershipRemovalSerializer(
            data={"organization": organization_id},
            context={"request": request, "user": target},
        )
        serializer.is_valid(raise_exception=True)
        serializer.remove()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"], url_path="switch-organization")
    def switch_organization(self, request):
        organization_id = request.data.get("organization")
        if organization_id is None:
            raise InvalidUserData(detail="Organization identifier is required.")
        try:
            membership = UserOrganization.objects.get(user=request.user, organization_id=organization_id)
        except UserOrganization.DoesNotExist as exc:
            raise InsufficientPermissions() from exc
        if not membership.is_active or membership.deleted_at is not None:
            raise InsufficientPermissions()
        request.session["active_organization_id"] = membership.organization_id
        return Response({"organization": membership.organization_id}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        read = UserReadSerializer(user, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserReadSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = UserReadSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_object(self):
        try:
            return super().get_object()
        except Exception as exc:
            raise UserNotFound() from exc
