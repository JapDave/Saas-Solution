from __future__ import annotations
from dataclasses import dataclass
from django.db import transaction
from .models import Organization


@dataclass
class ServiceResult:
    ok: bool
    organization: Organization | None = None
    error: str | None = None
    details: dict | None = None


@transaction.atomic
def create_organization(*, account, name: str, description: str = "", logo_url: str = "", created_by=None) -> ServiceResult:
    org = Organization(account=account, name=name, description=description, logo_url=logo_url,
                       created_by=created_by, updated_by=created_by)
    org.full_clean()
    org.save()
    return ServiceResult(ok=True, organization=org)


@transaction.atomic
def update_organization(*, organization: Organization, **fields) -> ServiceResult:
    for k, v in fields.items():
        if v is not None:
            setattr(organization, k, v)
    organization.full_clean()
    organization.save()
    return ServiceResult(ok=True, organization=organization)


@transaction.atomic
def delete_organization(*, organization: Organization) -> ServiceResult:
    if organization.deleted_at:
        return ServiceResult(ok=True, organization=organization)
    organization.delete()  # BaseModel should soft-delete
    return ServiceResult(ok=True, organization=organization)
