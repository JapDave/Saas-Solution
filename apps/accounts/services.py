from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from .models import Account


@dataclass
class ServiceResult:
    """Return object describing the outcome of an account service call."""

    ok: bool
    account: Account | None = None
    error: str | None = None
    details: dict | None = None


@transaction.atomic
def create_account(*, name: str, contact_email: str, description: str = "", created_by=None) -> ServiceResult:
    """Create a new account record and wrap the result in :class:`ServiceResult`."""

    account = Account(
        name=name,
        contact_email=contact_email,
        description=description,
        created_by=created_by,
        updated_by=created_by,
    )
    account.full_clean()
    account.save()
    return ServiceResult(ok=True, account=account)


@transaction.atomic
def update_account(*, account: Account, **fields) -> ServiceResult:
    """Update ``account`` with the provided ``fields`` and return the persisted instance."""

    for key, value in fields.items():
        if value is not None:
            setattr(account, key, value)
    account.full_clean()
    account.save()
    return ServiceResult(ok=True, account=account)


@transaction.atomic
def delete_account(*, account: Account) -> ServiceResult:
    """Soft-delete the provided ``account`` if it has not already been archived."""

    if account.deleted_at:
        return ServiceResult(ok=True, account=account)
    account.delete()
    return ServiceResult(ok=True, account=account)
