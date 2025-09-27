from __future__ import annotations
from dataclasses import dataclass
from django.db import transaction
from .models import Account

@dataclass
class ServiceResult:
    ok: bool
    account: Account | None = None
    error: str | None = None
    details: dict | None = None

@transaction.atomic
def create_account(*, name: str, contact_email: str, description: str = "", created_by=None) -> ServiceResult:
    acc = Account(name=name, contact_email=contact_email, description=description, created_by=created_by, updated_by=created_by)
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
def delete_account(*, account: Account) -> ServiceResult:
    if account.deleted_at:
        return ServiceResult(ok=True, account=account)
    account.delete()  # BaseModel should soft-delete
    return ServiceResult(ok=True, account=account)
