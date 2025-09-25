from __future__ import annotations
from rest_framework import viewsets, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from .models import Account
from .serializers import (
    AccountCreateSerializer,
    AccountUpdateSerializer,
    AccountReadSerializer,
)
from .permissions import IsSaaSAdminOrStaff


class AccountViewSet(viewsets.ModelViewSet):
    """
    CRUD only:
      - POST   /accounts/            (create)
      - GET    /accounts/            (list)
      - GET    /accounts/{id}/       (retrieve)
      - PUT    /accounts/{id}/       (update)         <- can toggle is_active here
      - PATCH  /accounts/{id}/       (partial update) <- can toggle is_active here
      - DELETE /accounts/{id}/       (soft delete)
    """
    queryset = Account.objects.order_by("-created_at")  # default manager hides soft-deleted rows
    permission_classes = [IsSaaSAdminOrStaff]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ["created_at", "updated_at", "name"]

    def get_serializer_class(self):
        if self.action == "create":
            return AccountCreateSerializer
        if self.action in ("update", "partial_update"):
            return AccountUpdateSerializer
        return AccountReadSerializer

    # CREATE
    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        account = Account(**ser.validated_data)
        account.created_by = request.user
        account.updated_by = request.user
        account.full_clean()
        account.save()
        return Response(AccountReadSerializer(account).data, status=status.HTTP_201_CREATED)

    # UPDATE / PARTIAL_UPDATE (includes toggling is_active)
    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, partial: bool):
        try:
            account = Account.objects.get(pk=self.kwargs["pk"])
        except Account.DoesNotExist:
            return Response({"code": "ACCOUNT_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        ser = self.get_serializer(account, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)

        for field, value in ser.validated_data.items():
            setattr(account, field, value)

        account.updated_by = request.user
        account.full_clean()
        account.save()
        return Response(AccountReadSerializer(account).data)

    # DELETE (soft)
    def destroy(self, request, *args, **kwargs):
        try:
            account = Account.objects.get(pk=self.kwargs["pk"])
        except Account.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)
        account.delete()  # soft delete via model
        return Response(status=status.HTTP_204_NO_CONTENT)
