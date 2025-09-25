from dataclasses import dataclass
from typing import Iterable
from django.db import transaction

from accounts.models import Account

@dataclass
class ServiceResult:
    ok: bool
    account: Account | None = None
    error: str | None = None
    details: dict | None = None

# def _org_ids_for_account(account: Account) -> Iterable:
#     # Lazy import to avoid circular deps
#     from apps.organizations.models import Organization
#     return Organization.objects.filter(account=account).values_list("id", flat=True)

# def _has_active_subscriptions(account: Account) -> bool:
#     from apps.subscriptions.models import Subscription
#     org_ids = list(_org_ids_for_account(account))
#     if not org_ids:
#         return False
#     return Subscription.objects.filter(
#         org_id__in=org_ids, state__in=["active", "trial"]
#     ).exists()

@transaction.atomic
def create_account(*, name: str, contact_email: str, description: str = "", created_by=None) -> ServiceResult:
    acc = Account(name=name, contact_email=contact_email, description=description, created_by=created_by)
    acc.full_clean()
    acc.save()
    return ServiceResult(ok=True, account=acc)

@transaction.atomic
def update_account(*, account: Account, **fields) -> ServiceResult:
    for k, v in fields.items():
        if v is not None:
            setattr(account, k, v)
    account.full_clean()
    account.save()
    return ServiceResult(ok=True, account=account)

@transaction.atomic
def deactivate_account(*, account: Account) -> ServiceResult:
    if account.deleted_at:
        return ServiceResult(ok=False, error="ACCOUNT_DELETED")
    if not account.is_active:
        return ServiceResult(ok=True, account=account)
    # if _has_active_subscriptions(account):
    #     return ServiceResult(
    #         ok=False,
    #         error="ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS",
    #         details={"message": "Deactivate or cancel org subscriptions first."},
    #     )
    account.is_active = False
    account.save(update_fields=["is_active", "updated_at"])
    return ServiceResult(ok=True, account=account)

@transaction.atomic
def activate_account(*, account: Account) -> ServiceResult:
    if account.deleted_at:
        return ServiceResult(ok=False, error="ACCOUNT_DELETED")
    if account.is_active:
        return ServiceResult(ok=True, account=account)
    account.is_active = True
    account.save(update_fields=["is_active", "updated_at"])
    return ServiceResult(ok=True, account=account)

@transaction.atomic
def delete_account(*, account: Account) -> ServiceResult:
    if account.deleted_at:
        return ServiceResult(ok=True, account=account)
    # if _has_active_subscriptions(account):
    #     return ServiceResult(ok=False, error="ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS")
    account.soft_delete()
    return ServiceResult(ok=True, account=account)
