from __future__ import annotations

from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status, viewsets
from rest_framework.filters import OrderingFilter
from rest_framework.response import Response

from apps.common.paginations import StandardPagination
from apps.common.permissions import get_assigned_account_ids
from apps.roles.permissions import AccountPermission
from apps.common.exceptions import AccountNotFound
from apps.subscriptions.services import ensure_account_has_no_active_subscriptions

from .models import Account
from .serializers import AccountCreateSerializer, AccountUpdateSerializer, AccountReadSerializer


class AccountViewSet(viewsets.ModelViewSet):
    """Account API wiring: pagination/filtering plus role-aware permissions."""
    queryset = Account.objects.order_by("-created_at")
    permission_classes = [AccountPermission]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "updated_at", "name"]
    filterset_fields = ["is_active"]

    # Use UUID in URLs instead of integer pk
    lookup_field = "uuid"              # /api/accounts/<uuid>/
    lookup_url_kwarg = "uuid"          # router will pass as kwargs["uuid"]

    def get_queryset(self):
        qs = Account.objects.order_by("-created_at")
        user = getattr(self.request, "user", None)
        if not (user and user.is_authenticated):
            return qs.none()
        if user.is_superuser:
            return qs
        if user.is_staff:
            assigned = get_assigned_account_ids(user)
            if not assigned:
                return qs.none()
            return qs.filter(id__in=assigned)
        return qs.filter(created_by_id=user.id)

    def get_serializer_class(self):
        if self.action == "create":
            return AccountCreateSerializer
        if self.action in ("update", "partial_update"):
            return AccountUpdateSerializer
        return AccountReadSerializer

    # CREATE -> respond with read shape
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = ser.save(created_by=request.user, updated_by=request.user)
        return Response(AccountReadSerializer(obj).data, status=status.HTTP_201_CREATED)

    # UPDATE/PATCH -> respond with read shape
    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, *, partial: bool):
        try:
            obj = self.get_object()  # respects lookup_field=uuid
        except Http404:
            # coded 404
            raise AccountNotFound()

        ser = self.get_serializer(obj, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        obj = ser.save(updated_by=request.user)
        return Response(AccountReadSerializer(obj).data, status=status.HTTP_200_OK)

    # DELETE (soft)
    def destroy(self, request, *args, **kwargs):
        try:
            obj = self.get_object()  # respects lookup_field=uuid
        except Http404:
            # coded 404
            raise AccountNotFound()

        ensure_account_has_no_active_subscriptions(obj)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)






