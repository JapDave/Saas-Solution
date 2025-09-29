import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AccountFactory
from apps.organizations.tests.factories import OrganizationFactory
from apps.users.tests.factories import UserFactory, StaffUserFactory, SuperUserFactory


# ---------------------------------------------------------------------------
# Global test settings (domain allowlist for staff/superusers)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _allow_staff_domains(settings):
    """Ensure staff/superuser email domain checks never fail in tests."""
    allowed = ["hudhud.ai", "example.com", "test.com", "local.test"]
    settings.ALLOWED_STAFF_EMAIL_DOMAINS = allowed
    settings.ALLOWED_SYSTEM_EMAIL_DOMAINS = allowed
    settings.ALLOWED_ADMIN_EMAIL_DOMAINS = allowed
    settings.ALLOWED_EMAIL_DOMAINS = allowed


# ---------------------------------------------------------------------------
# API clients
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    return APIClient()


def _authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ---------------------------------------------------------------------------
# Users / Roles
# ---------------------------------------------------------------------------

@pytest.fixture
@pytest.mark.django_db
def superadmin_user():
    return SuperUserFactory(email="superadmin@hudhud.ai")


@pytest.fixture
@pytest.mark.django_db
def manager_user():
    return StaffUserFactory(email="manager@hudhud.ai")


@pytest.fixture
@pytest.mark.django_db
def regular_user():
    return UserFactory(email="user@example.com")


# Clients for each role
@pytest.fixture
def superadmin_client(superadmin_user):
    return _authed_client(superadmin_user)


@pytest.fixture
def manager_client(manager_user):
    from apps.accounts.models import Account

    manager_user.get_assigned_account_ids = lambda: list(Account.objects.values_list("id", flat=True))
    return _authed_client(manager_user)


@pytest.fixture
def regular_client(regular_user):
    return _authed_client(regular_user)


@pytest.fixture
def unauth_client():
    return APIClient()


# ---------------------------------------------------------------------------
# Backward-compatible aliases (existing tests using admin_* keep working)
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(superadmin_user):
    return superadmin_user


@pytest.fixture
def admin_client(superadmin_client):
    return superadmin_client


# ---------------------------------------------------------------------------
# Data fixtures (Accounts & Organizations)
# ---------------------------------------------------------------------------

@pytest.fixture
@pytest.mark.django_db
def acc_a(admin_user):
    return AccountFactory(
        name="Acme",
        contact_email="owner@acme.com",
        description="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def acc_b(admin_user):
    return AccountFactory(
        name="Beta Co",
        contact_email="ops@beta.co",
        description="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def acc_owned_by_user(regular_user):
    return AccountFactory(
        name="UserCo",
        contact_email="userco@example.com",
        description="",
        created_by=regular_user,
        updated_by=regular_user,
    )


@pytest.fixture
@pytest.mark.django_db
def org_a(acc_a):
    return OrganizationFactory(account=acc_a, name="Alpha", description="")


@pytest.fixture
@pytest.mark.django_db
def org_b(acc_a):
    return OrganizationFactory(account=acc_a, name="Bravo", description="")


@pytest.fixture
@pytest.mark.django_db
def org_c_in_b(acc_b):
    return OrganizationFactory(account=acc_b, name="Charlie", description="")


@pytest.fixture
@pytest.mark.django_db
def org_owned_by_user(acc_owned_by_user, regular_user):
    return OrganizationFactory(
        account=acc_owned_by_user,
        name="UserOrg",
        description="",
        created_by=regular_user,
        updated_by=regular_user,
    )


# ---------------------------------------------------------------------------
# Manager assignment helpers (no schema change required)
# ---------------------------------------------------------------------------

@pytest.fixture
def manager_client_assigned_acc_a(manager_user, acc_a):
    manager_user.get_assigned_account_ids = lambda: [acc_a.id]
    return _authed_client(manager_user)


@pytest.fixture
def manager_client_with_no_assignments(manager_user):
    manager_user.get_assigned_account_ids = lambda: []
    return _authed_client(manager_user)
