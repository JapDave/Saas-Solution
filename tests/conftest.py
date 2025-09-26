import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


def _authed_client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


# ---- Users / Roles ---------------------------------------------------------

@pytest.fixture
@pytest.mark.django_db
def admin_user():
    # SaaS admin (DRF admin) = superuser; staff True for admin site too
    return User.objects.create_user(
        email="admin@hudhud.ai",
        password="pass1234",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
@pytest.mark.django_db
def manager_user():
    # Manager = staff user (assigned scoping will be handled later)
    return User.objects.create_user(
        email="manager@hudhud.ai",
        password="pass1234",
        is_staff=True,
        # not superuser
    )


@pytest.fixture
@pytest.mark.django_db
def regular_user():
    # Normal end-user (no staff, no superuser)
    return User.objects.create_user(
        email="user@example.com",
        password="pass1234",
    )


@pytest.fixture
def admin_client(admin_user):
    return _authed_client(admin_user)


@pytest.fixture
def manager_client(manager_user):
    return _authed_client(manager_user)


@pytest.fixture
def regular_client(regular_user):
    return _authed_client(regular_user)


@pytest.fixture
def unauth_client():
    return APIClient()
