import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.organizations.models import Organization

User = get_user_model()


# ---------------------------------------------------------------------------
# Global test settings (domain allowlist for staff/superusers)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _allow_staff_domains(settings):
    """
    Your User model restricts staff/superuser emails to certain domains.
    Keep tests stable by allowing a small set; adjust names if your code
    reads a single canonical setting.
    """
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
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ---------------------------------------------------------------------------
# Users / Roles
# ---------------------------------------------------------------------------

def _make_user(email, *, is_superuser=False, is_staff=False, password="pass1234", **extra):
    return User.objects.create_user(
        email=email,
        password=password,
        is_superuser=is_superuser,
        is_staff=is_staff,
        **extra,
    )


@pytest.fixture
@pytest.mark.django_db
def superadmin_user():
    # System SuperAdmin — full power
    return _make_user("superadmin@hudhud.ai", is_superuser=True, is_staff=True)


@pytest.fixture
@pytest.mark.django_db
def manager_user():
    # Manager — privileged but not superuser
    return _make_user("manager@hudhud.ai", is_superuser=False, is_staff=True)


@pytest.fixture
@pytest.mark.django_db
def regular_user():
    # Regular end-user — no staff/superuser flags
    return _make_user("user@example.com", is_superuser=False, is_staff=False)


# Clients for each role
@pytest.fixture
def superadmin_client(superadmin_user):
    return _authed_client(superadmin_user)


@pytest.fixture
def manager_client(manager_user):
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
    return Account.objects.create(
        name="Acme",
        contact_email="owner@acme.com",
        description="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def acc_b(admin_user):
    return Account.objects.create(
        name="Beta Co",
        contact_email="ops@beta.co",
        description="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def acc_owned_by_user(regular_user):
    return Account.objects.create(
        name="UserCo",
        contact_email="userco@example.com",
        description="",
        created_by=regular_user,
        updated_by=regular_user,
    )


@pytest.fixture
@pytest.mark.django_db
def org_a(acc_a, admin_user):
    return Organization.objects.create(
        account=acc_a,
        name="Alpha",
        description="",
        logo_url="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def org_b(acc_a, admin_user):
    return Organization.objects.create(
        account=acc_a,
        name="Bravo",
        description="",
        logo_url="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def org_c_in_b(acc_b, admin_user):
    return Organization.objects.create(
        account=acc_b,
        name="Charlie",
        description="",
        logo_url="",
        created_by=admin_user,
        updated_by=admin_user,
    )


@pytest.fixture
@pytest.mark.django_db
def org_owned_by_user(acc_owned_by_user, regular_user):
    return Organization.objects.create(
        account=acc_owned_by_user,
        name="UserOrg",
        description="",
        logo_url="",
        created_by=regular_user,
        updated_by=regular_user,
    )


# ---------------------------------------------------------------------------
# Manager assignment helpers (no schema change required)
# ---------------------------------------------------------------------------

@pytest.fixture
def manager_client_assigned_acc_a(manager_user, acc_a):
    """
    Attach a lightweight get_assigned_account_ids() to the same user instance
    used for authentication so permissions can resolve assignments.
    """
    manager_user.get_assigned_account_ids = lambda: [acc_a.id]
    return _authed_client(manager_user)


@pytest.fixture
def manager_client_with_no_assignments(manager_user):
    manager_user.get_assigned_account_ids = lambda: []
    return _authed_client(manager_user)
