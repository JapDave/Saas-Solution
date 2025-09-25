from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from accounts.models import Account
from .permissions import IsSaaSAdminOrStaff
from .serializers import (
    AccountReadSerializer,
    AccountWriteSerializer,
    AccountUpdateSerializer,
)
from .filters import AccountFilter
from accounts import selectors, services

class AccountViewSet(viewsets.ModelViewSet):
    """Account CRUD + lifecycle. Restricted to SaaS Admin or staff. DELETE is soft delete."""
    queryset = Account.objects.not_deleted().order_by("-created_at")
    serializer_class = AccountReadSerializer
    permission_classes = [IsSaaSAdminOrStaff]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AccountFilter
    ordering_fields = ["created_at", "updated_at", "name"]

    def get_serializer_class(self):
        if self.action == "create":
            return AccountWriteSerializer
        if self.action in ("update", "partial_update"):
            return AccountUpdateSerializer
        return AccountReadSerializer

    def create(self, request, *args, **kwargs):
        ser = self.get_serializer(data=request.data)
        ser.is_valid(raise_exception=True)
        res = services.create_account(
            name=ser.validated_data.get("name"),
            description=ser.validated_data.get("description", ""),
            contact_email=ser.validated_data.get("contact_email"),
            created_by=request.user,
        )
        if not res.ok:
            return Response({"code": res.error, "details": res.details}, status=status.HTTP_400_BAD_REQUEST)
        out = AccountReadSerializer(res.account)
        headers = self.get_success_headers(out.data)
        return Response(out.data, status=status.HTTP_201_CREATED, headers=headers)

    def retrieve(self, request, *args, **kwargs):
        acc = selectors.get_account_by_id(kwargs["pk"])
        if not acc:
            return Response({"code": "ACCOUNT_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        return Response(AccountReadSerializer(acc).data)

    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, partial: bool):
        acc = selectors.get_account_by_id(self.kwargs["pk"])
        if not acc:
            return Response({"code": "ACCOUNT_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        ser = self.get_serializer(acc, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        res = services.update_account(account=acc, **ser.validated_data)
        if not res.ok:
            status_code = status.HTTP_409_CONFLICT if res.error and "EXISTS" in res.error else status.HTTP_400_BAD_REQUEST
            return Response({"code": res.error, "details": res.details}, status=status_code)
        return Response(AccountReadSerializer(res.account).data)

    def destroy(self, request, *args, **kwargs):
        acc = selectors.get_account_by_id(kwargs["pk"])
        if not acc:
            return Response(status=status.HTTP_404_NOT_FOUND)
        res = services.delete_account(account=acc)
        if not res.ok:
            return Response({"code": res.error}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        acc = selectors.get_account_by_id(pk)
        if not acc:
            return Response({"code": "ACCOUNT_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        res = services.deactivate_account(account=acc)
        if not res.ok:
            return Response({"code": res.error, "details": res.details}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"accountId": str(acc.id), "state": acc.state, "isActive": acc.is_active})

    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        acc = selectors.get_account_by_id(pk)
        if not acc:
            return Response({"code": "ACCOUNT_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        res = services.activate_account(account=acc)
        if not res.ok:
            return Response({"code": res.error}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"accountId": str(acc.id), "state": acc.state, "isActive": acc.is_active})
