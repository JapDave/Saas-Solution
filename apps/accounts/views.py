from __future__ import annotations
from django.core.exceptions import ValidationError
from rest_framework import viewsets, status
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination

from .models import Account
from .serializers import AccountCreateSerializer, AccountUpdateSerializer, AccountReadSerializer
from .permissions import IsSaaSAdminOrStaff
from .services import create_account, update_account, delete_account

class StandardPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    # make absolutely sure '?page_size=' is honored
    def get_page_size(self, request):
        try:
            raw = request.query_params.get(self.page_size_query_param)
            if raw is not None:
                val = int(raw)
                if val > 0:
                    return min(val, self.max_page_size)
        except Exception:
            pass
        return self.page_size

class AccountViewSet(viewsets.ModelViewSet):
    """
    Simple CRUD only. Uses services for mutations.
    Auth: SaaS Admin (is_superuser) or Manager (is_staff).
    """
    queryset = Account.objects.order_by("-created_at")
    permission_classes = [IsSaaSAdminOrStaff]
    pagination_class = StandardPagination
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
        try:
            result = create_account(
                name=ser.validated_data["name"],
                contact_email=ser.validated_data["contact_email"],
                description=ser.validated_data.get("description", ""),
                created_by=request.user,
            )
        except ValidationError as e:
            return Response(e.message_dict or {"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AccountReadSerializer(result.account).data, status=status.HTTP_201_CREATED)

    # UPDATE / PARTIAL_UPDATE
    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, partial: bool):
        try:
            account = Account.objects.get(pk=self.kwargs["pk"])
        except Account.DoesNotExist:
            return Response({"code": "ACCOUNT_NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        # Strict type guard to satisfy test: reject non-string name early
        if "name" in request.data and not isinstance(request.data["name"], str):
            return Response({"name": ["Must be a string."]}, status=status.HTTP_400_BAD_REQUEST)

        ser = self.get_serializer(account, data=request.data, partial=partial)
        ser.is_valid(raise_exception=True)

        try:
            result = update_account(account=account, **ser.validated_data)
        except ValidationError as e:
            return Response(e.message_dict or {"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AccountReadSerializer(result.account).data, status=status.HTTP_200_OK)

    # DELETE (soft)
    def destroy(self, request, *args, **kwargs):
        try:
            account = Account.objects.get(pk=self.kwargs["pk"])
        except Account.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND)

        delete_account(account=account)
        return Response(status=status.HTTP_204_NO_CONTENT)
