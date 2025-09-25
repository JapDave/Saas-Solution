from typing import Optional
from django.db.models import QuerySet
from accounts.models import Account

def get_account_by_id(account_id) -> Optional[Account]:
    return Account.objects.not_deleted().filter(id=account_id).first()

def list_accounts(q: str | None = None, is_active: bool | None = None) -> QuerySet[Account]:
    qs = Account.objects.not_deleted()
    if q:
        qs = qs.search(q)
    if is_active is True:
        qs = qs.filter(is_active=True)
    elif is_active is False:
        qs = qs.exclude(is_active=True)
    return qs.order_by("-created_at")
