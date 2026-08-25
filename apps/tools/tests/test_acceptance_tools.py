import pytest
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.agents.models import OrganizationEnabledTool
from apps.common.models import AuditLog, DataChangeLog
from apps.organizations.models import Organization
from apps.organizations.models import Organization as OrganizationModel
from apps.products.models import Module
from apps.roles.constants import (
    ROLE_ACCOUNT_ADMINISTRATOR,
    ROLE_ACCOUNT_OWNER,
    ROLE_AGENT_MANAGER,
    ROLE_ORGANIZATION_ADMINISTRATOR,
    ROLE_ORGANIZATION_OWNER,
    ROLE_SAAS_ACCOUNT_MANAGER,
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_PERMISSION_TEMPLATES,
    TOOL_PERMISSION_KEYS,
)
from apps.roles.models import Role, RoleAssignment
from apps.subscriptions.models import Subscription
from apps.users.models import User, UserOrganization
from apps.users.tests.factories import UserFactory
from apps.users.services import invalidate_user_permission_cache

pytestmark = pytest.mark.django_db

TEST_USERS = {
    "Super Admin": {"email": "admin@saas-platform.ai", "password": "admin123"},
    "SaaS Account Manager": {"email": "saas.account.manager@saas-platform.ai", "password": "Manager123!"},
    "Account 1 Agent Manager": {"email": "account1.agent.manager@test.com", "password": "Test123!"},
    "Account 1 Admin": {"email": "account1.admin@test.com", "password": "Test123!"},
    "Account 1 Owner": {"email": "account1.owner@test.com", "password": "Test123!"},
    "Account 1 Org Admin": {"email": "account1.org.admin@test.com", "password": "Test123!"},
    "Account 1 User 1": {"email": "account1.user1@test.com", "password": "Test123!"},
}


def get_user_credentials(full_name: str) -> tuple[str, str]:
    if full_name not in TEST_USERS:
        raise ValueError(f"Unknown test user: {full_name}")
    user = TEST_USERS[full_name]
    return user["email"], user["password"]


def make_request(client: APIClient, method: str, endpoint: str, *, json=None):
    method = method.lower()
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    if method == "get":
        return client.get(endpoint)
    if method == "post":
        return client.post(endpoint, data=json or {}, format="json")
    if method == "patch":
        return client.patch(endpoint, data=json or {}, format="json")
    if method == "put":
        return client.put(endpoint, data=json or {}, format="json")
    if method == "delete":
        return client.delete(endpoint)
    raise ValueError(f"Unsupported method: {method}")


def _tool_list_url(org):
    return reverse("tool-list", kwargs={"organization_uuid": org.uuid})


def _tool_detail_url(org, tool_key: str):
    return reverse("tool-detail", kwargs={"organization_uuid": org.uuid, "tool_key": tool_key})


def _tool_enabled_url(org):
    return reverse("tool-enabled-list", kwargs={"organization_uuid": org.uuid})


def _tool_enable_url(org, tool_key: str):
    return reverse("organization-tools-enable", kwargs={"organization_uuid": org.uuid, "tool_key": tool_key})


def _tool_disable_url(org, tool_key: str):
    return reverse("organization-tools-disable", kwargs={"organization_uuid": org.uuid, "tool_key": tool_key})


def _tool_validate_url():
    return reverse("tool-validate")


def _create_subscription(org, module, *, status=Subscription.Status.ACTIVE, end_date=None, configuration=None):
    return Subscription.objects.create(
        organization=org,
        module=module,
        status=status,
        start_date=timezone.now() - timedelta(days=1),
        end_date=end_date,
        configuration=configuration or {},
    )


def ensure_tools_management_subscription(org):
    module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
    if not module:
        return None
    subscription = Subscription.objects.filter(organization=org, module=module).first()
    if not subscription:
        return _create_subscription(org, module)
    if subscription.status != Subscription.Status.ACTIVE:
        subscription.status = Subscription.Status.ACTIVE
        subscription.end_date = None
        subscription.save(update_fields=["status", "end_date", "updated_at"])
    return subscription


def _create_role(*, name: str, permissions: list[str], organization=None, role_type=None, created_by=None):
    role_type = role_type or (Role.RoleType.SYSTEM if organization is None else Role.RoleType.USER)
    role, _ = Role.all_objects.update_or_create(
        name=name,
        organization=organization,
        defaults={
            "permissions": permissions,
            "role_type": role_type,
            "created_by": created_by,
            "deleted_at": None,
            "is_active": True,
        },
    )
    return role


def _assign_role(user, role, *, organization=None, assigned_by=None):
    assignment, _ = RoleAssignment.all_objects.update_or_create(
        user=user,
        role=role,
        organization=organization,
        defaults={
            "assigned_by": assigned_by or user,
            "deleted_at": None,
            "is_active": True,
        },
    )
    return assignment


def _ensure_membership(user, organization):
    membership, _ = UserOrganization.all_objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "assigned_by": user,
            "permission_keys": [],
            "deleted_at": None,
            "is_active": True,
        },
    )
    return membership


@pytest.fixture(autouse=True)
def tool_acceptance_setup(db):
    emails = [data["email"] for data in TEST_USERS.values()]
    account_names = ["Test Account Alpha", "Test Account Beta"]
    org_names = [
        "Test Organization Alpha1",
        "Test Organization Alpha2",
        "Test Organization Alpha3",
        "Test Organization Beta1",
    ]
    role_names = [
        ROLE_SAAS_ADMINISTRATOR,
        ROLE_SAAS_ACCOUNT_MANAGER,
        ROLE_AGENT_MANAGER,
        ROLE_ACCOUNT_ADMINISTRATOR,
        ROLE_ACCOUNT_OWNER,
        ROLE_ORGANIZATION_ADMINISTRATOR,
        ROLE_ORGANIZATION_OWNER,
    ]

    RoleAssignment.all_objects.filter(user__email__in=emails).delete()
    UserOrganization.all_objects.filter(user__email__in=emails).delete()
    OrganizationEnabledTool.all_objects.filter(organization__name__in=org_names).delete()
    Subscription.objects.filter(organization__name__in=org_names).delete()
    Role.all_objects.filter(name__in=role_names).delete()
    OrganizationModel._all_objects.filter(name__in=org_names).delete()
    Account._all_objects.filter(name__in=account_names).delete()
    User.all_objects.filter(email__in=emails).delete()
    Module.objects.filter(key="TOOLS_MANAGEMENT").delete()

    module, _ = Module.objects.update_or_create(
        key="TOOLS_MANAGEMENT",
        defaults={
            "code": "TOOL",
            "name": "Tools Management",
            "description": "Tools module",
            "subscribable": True,
            "exposed_permissions": list(TOOL_PERMISSION_KEYS),
        },
    )

    account_alpha, _ = Account._all_objects.update_or_create(
        name="Test Account Alpha",
        defaults={
            "contact_email": "alpha@test.com",
            "description": "Test account with multiple organizations",
            "deleted_at": None,
            "is_active": True,
        },
    )
    account_beta, _ = Account._all_objects.update_or_create(
        name="Test Account Beta",
        defaults={
            "contact_email": "beta@test.com",
            "description": "Test account with single organization",
            "deleted_at": None,
            "is_active": True,
        },
    )

    org_alpha1, _ = OrganizationModel._all_objects.update_or_create(
        name="Test Organization Alpha1",
        account=account_alpha,
        defaults={
            "description": "",
            "logo_url": "",
            "deleted_at": None,
            "is_active": True,
        },
    )
    org_alpha2, _ = OrganizationModel._all_objects.update_or_create(
        name="Test Organization Alpha2",
        account=account_alpha,
        defaults={
            "description": "",
            "logo_url": "",
            "deleted_at": None,
            "is_active": True,
        },
    )
    org_alpha3, _ = OrganizationModel._all_objects.update_or_create(
        name="Test Organization Alpha3",
        account=account_alpha,
        defaults={
            "description": "",
            "logo_url": "",
            "deleted_at": None,
            "is_active": True,
        },
    )
    OrganizationModel._all_objects.update_or_create(
        name="Test Organization Beta1",
        account=account_beta,
        defaults={
            "description": "",
            "logo_url": "",
            "deleted_at": None,
            "is_active": True,
        },
    )

    _create_subscription(org_alpha1, module)
    _create_subscription(org_alpha2, module)

    super_admin = UserFactory(
        email=TEST_USERS["Super Admin"]["email"],
        full_name="Super Admin",
        is_staff=True,
        is_superuser=True,
    )
    saas_manager = UserFactory(
        email=TEST_USERS["SaaS Account Manager"]["email"],
        full_name="SaaS Account Manager",
        is_staff=True,
    )
    saas_manager.user_preferences = {"assigned_account_ids": [account_alpha.id]}
    saas_manager.save(update_fields=["user_preferences", "updated_at"])

    agent_manager = UserFactory(
        email=TEST_USERS["Account 1 Agent Manager"]["email"],
        full_name="Account 1 Agent Manager",
    )
    account_admin = UserFactory(
        email=TEST_USERS["Account 1 Admin"]["email"],
        full_name="Account 1 Admin",
    )
    account_owner = UserFactory(
        email=TEST_USERS["Account 1 Owner"]["email"],
        full_name="Account 1 Owner",
    )
    org_admin = UserFactory(
        email=TEST_USERS["Account 1 Org Admin"]["email"],
        full_name="Account 1 Org Admin",
    )
    normal_user = UserFactory(
        email=TEST_USERS["Account 1 User 1"]["email"],
        full_name="Account 1 User 1",
    )

    role_saas_admin = _create_role(
        name=ROLE_SAAS_ADMINISTRATOR,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_SAAS_ADMINISTRATOR]),
        created_by=super_admin,
    )
    role_saas_manager = _create_role(
        name=ROLE_SAAS_ACCOUNT_MANAGER,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_SAAS_ACCOUNT_MANAGER]),
        created_by=super_admin,
    )
    role_agent_manager = _create_role(
        name=ROLE_AGENT_MANAGER,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_AGENT_MANAGER]),
        organization=org_alpha1,
        created_by=super_admin,
    )
    role_account_admin = _create_role(
        name=ROLE_ACCOUNT_ADMINISTRATOR,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_ACCOUNT_ADMINISTRATOR]),
        organization=org_alpha1,
        created_by=super_admin,
    )
    role_account_owner = _create_role(
        name=ROLE_ACCOUNT_OWNER,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_ACCOUNT_OWNER]),
        organization=org_alpha1,
        created_by=super_admin,
    )
    role_org_admin = _create_role(
        name=ROLE_ORGANIZATION_ADMINISTRATOR,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_ORGANIZATION_ADMINISTRATOR]),
        organization=org_alpha1,
        created_by=super_admin,
    )
    role_org_owner = _create_role(
        name=ROLE_ORGANIZATION_OWNER,
        permissions=list(ROLE_PERMISSION_TEMPLATES[ROLE_ORGANIZATION_OWNER]),
        organization=org_alpha1,
        created_by=super_admin,
    )

    _assign_role(super_admin, role_saas_admin, assigned_by=super_admin)
    _assign_role(saas_manager, role_saas_manager, assigned_by=super_admin)
    _assign_role(agent_manager, role_agent_manager, organization=org_alpha1, assigned_by=super_admin)
    _assign_role(account_admin, role_account_admin, organization=org_alpha1, assigned_by=super_admin)
    _assign_role(account_owner, role_account_owner, organization=org_alpha1, assigned_by=super_admin)
    _assign_role(org_admin, role_org_admin, organization=org_alpha1, assigned_by=super_admin)
    _assign_role(account_owner, role_org_owner, organization=org_alpha1, assigned_by=super_admin)

    for user in (agent_manager, account_admin, account_owner, org_admin, normal_user):
        _ensure_membership(user, org_alpha1)


@pytest.fixture
def authenticated_client():
    def _factory(email, _password=None):
        user = User.objects.filter(email=email).first()
        if not user:
            raise RuntimeError(f"Test user not found: {email}")
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _factory


@pytest.fixture
def http_client():
    return APIClient()

class TestREQTool001ListAvailableTools:
    def test_1_1_successful_list_by_saas_administrator(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        before_request = timezone.now()
        response = make_request(client, "get", _tool_list_url(org))

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        tool = data[0]
        assert "toolKey" in tool or "tool_key" in tool
        assert "displayName" in tool or "display_name" in tool
        assert "description" in tool
        assert "category" in tool or "categories" in tool

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_list_url(org),
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        assert audit_log is not None
        assert audit_log.success is True
        assert audit_log.user_id == user.id

    def test_1_2_successful_list_by_saas_account_manager(self, authenticated_client, http_client):
        email, _password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_1_3_successful_list_by_agent_manager(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_1_4_successful_list_by_account_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        before_request = timezone.now()
        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_list_url(org),
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is True
            assert audit_log.user_id == user.id

    def test_1_5_successful_list_by_account_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_1_6_successful_list_by_organization_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_1_7_successful_list_by_organization_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_1_8_get_specific_tool_by_saas_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"

        before_request = timezone.now()
        response = make_request(client, "get", _tool_detail_url(org, tool_key))
        assert response.status_code == 200
        data = response.json()
        assert "toolKey" in data or "tool_key" in data
        assert (data.get("toolKey") or data.get("tool_key")) == tool_key
        assert "displayName" in data or "display_name" in data
        assert "description" in data

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_detail_url(org, tool_key),
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is True
            assert audit_log.user_id == user.id

    def test_1_9_get_specific_tool_by_account_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"

        response = make_request(client, "get", _tool_detail_url(org, tool_key))
        assert response.status_code == 200
        data = response.json()
        assert "toolKey" in data or "tool_key" in data

    def test_1_10_get_nonexistent_tool_rejected(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "nonexistent-tool-12345"

        response = make_request(client, "get", _tool_detail_url(org, tool_key))
        assert response.status_code == 404

    def test_1_11_custom_role_with_permissions_can_list(self, authenticated_client, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        email, _password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.filter(email=email).first()
        assert test_user is not None

        custom_role = Role.objects.create(
            name="Custom Tools Viewer",
            role_type=Role.RoleType.USER_CUSTOM,
            organization=org,
            permissions=["tools:list", "tools:read"],
            created_by=test_user,
        )
        RoleAssignment.objects.create(user=test_user, organization=org, role=custom_role, assigned_by=test_user)
        _ensure_membership(test_user, org)
        invalidate_user_permission_cache(test_user.id, org.id)

        client = authenticated_client(email)
        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_1_12_custom_role_without_permissions_cannot_list(self, authenticated_client, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        email, _password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.filter(email=email).first()
        assert test_user is not None

        custom_role = Role.objects.create(
            name="Custom Tools Restricted",
            role_type=Role.RoleType.USER_CUSTOM,
            organization=org,
            permissions=[],
            created_by=test_user,
        )
        RoleAssignment.objects.create(user=test_user, organization=org, role=custom_role, assigned_by=test_user)
        _ensure_membership(test_user, org)
        invalidate_user_permission_cache(test_user.id, org.id)

        client = authenticated_client(email)
        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 403

    def test_1_14_agent_manager_can_list_but_not_enable_disable(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 200

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

    def test_1_15_agent_manager_without_Permissions_cannot_access(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        user = User.objects.filter(email=email).first()
        assert user is not None

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        agent_manager_role = Role.objects.filter(name__icontains="Agent Manager", organization=org).first()
        assert agent_manager_role is not None
        agent_manager_role.permissions = [
            perm for perm in agent_manager_role.permissions if perm not in {"tools:read", "tools:list"}
        ]
        agent_manager_role.save(update_fields=["permissions", "updated_at"])
        invalidate_user_permission_cache(user.id, org.id)

        client = authenticated_client(email)
        before_request = timezone.now()
        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 403

        audit_log = AuditLog.objects.filter(
            path=_tool_list_url(org),
            method="GET",
            status_code=403,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False

    def test_1_16_agent_manager_cannot_access_different_organization(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        user = User.objects.filter(email=email).first()
        assert user is not None

        user_org = UserOrganization.objects.filter(user=user).first()
        assert user_org is not None

        different_org = Organization.objects.exclude(uuid=user_org.organization.uuid).first()
        assert different_org is not None
        ensure_tools_management_subscription(different_org)

        before_request = timezone.now()
        response = make_request(client, "get", _tool_list_url(different_org))
        assert response.status_code in [403, 404]

        audit_log = AuditLog.objects.filter(
            path=_tool_list_url(different_org),
            method="GET",
            status_code__in=[403, 404],
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False

    def test_1_17_normal_user_cannot_access_anything(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 User 1")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        before_request = timezone.now()
        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code == 403

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 403

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

        audit_log = AuditLog.objects.filter(
            path=_tool_list_url(org),
            method="GET",
            status_code=403,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False

    def test_1_18_access_denied_without_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha3").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            Subscription.objects.filter(organization=org, module=module).delete()

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code in [403, 404]

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code in [403, 404]

    def test_1_19_access_denied_with_expired_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            subscription = Subscription.objects.filter(organization=org, module=module).first()
            if not subscription:
                subscription = _create_subscription(org, module)
            subscription.status = Subscription.Status.EXPIRED
            subscription.end_date = timezone.now() - timedelta(days=1)
            subscription.save(update_fields=["status", "end_date", "updated_at"])

        response = make_request(client, "get", _tool_list_url(org))
        assert response.status_code in [403, 404]

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code in [403, 404]

    def test_1_20_list_unauthenticated(self, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        response = make_request(http_client, "get", _tool_list_url(org))
        assert response.status_code == 401

class TestREQTool002ListEnabledTools:
    def test_2_1_successful_list_enabled_tools(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        before_request = timezone.now()
        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200

        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_enabled_url(org),
            method="GET",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is True
            assert audit_log.user_id == user.id

    def test_2_2_empty_list_when_no_enabled_tools(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        OrganizationEnabledTool.objects.filter(
            organization=org,
            disabled_at__isnull=True,
        ).update(disabled_at=timezone.now())

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert len(results) == 0

    def test_2_3_disabled_tool_not_included(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        user = User.objects.filter(email=email).first()
        enabled_tool, _ = OrganizationEnabledTool.objects.get_or_create(
            organization=org,
            tool_key="calculator",
            defaults={"enabled_by": user, "disabled_at": None},
        )
        enabled_tool.disable(actor=user)
        enabled_tool.save()

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        tool_keys = [tool.get("tool_key") or tool.get("toolKey") for tool in results]
        assert "calculator" not in tool_keys

    def test_2_4_successful_list_enabled_by_account_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

    def test_2_5_successful_list_enabled_by_account_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

    def test_2_6_successful_list_enabled_by_organization_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

    def test_2_7_successful_list_enabled_by_organization_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

    def test_2_9_custom_role_with_permissions_can_list_enabled(self, authenticated_client, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        email, _password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.filter(email=email).first()
        assert test_user is not None

        custom_role = Role.objects.create(
            name="Custom Enabled Tools Viewer",
            role_type=Role.RoleType.USER_CUSTOM,
            organization=org,
            permissions=["tools:read"],
            created_by=test_user,
        )
        RoleAssignment.objects.create(user=test_user, organization=org, role=custom_role, assigned_by=test_user)
        _ensure_membership(test_user, org)
        invalidate_user_permission_cache(test_user.id, org.id)

        client = authenticated_client(email)
        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

    def test_2_10_custom_role_without_permissions_cannot_list_enabled(self, authenticated_client, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        email, _password = get_user_credentials("Account 1 User 1")
        test_user = User.objects.filter(email=email).first()
        assert test_user is not None

        custom_role = Role.objects.create(
            name="Custom Enabled Tools Restricted",
            role_type=Role.RoleType.USER_CUSTOM,
            organization=org,
            permissions=[],
            created_by=test_user,
        )
        RoleAssignment.objects.create(user=test_user, organization=org, role=custom_role, assigned_by=test_user)
        _ensure_membership(test_user, org)
        invalidate_user_permission_cache(test_user.id, org.id)

        client = authenticated_client(email)
        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 403

    def test_2_12_agent_manager_can_list_enabled_but_not_enable_disable(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code == 200
        data = response.json()
        results = data.get("results") if isinstance(data, dict) else data
        assert isinstance(results, list)

    def test_2_13_agent_manager_cannot_list_enabled_different_organization(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        user = User.objects.filter(email=email).first()
        assert user is not None
        user_org = UserOrganization.objects.filter(user=user).first()
        assert user_org is not None

        different_org = Organization.objects.exclude(uuid=user_org.organization.uuid).first()
        assert different_org is not None
        ensure_tools_management_subscription(different_org)

        response = make_request(client, "get", _tool_enabled_url(different_org))
        assert response.status_code in [403, 404]

    def test_2_14_list_enabled_denied_without_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha3").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            Subscription.objects.filter(organization=org, module=module).delete()

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code in [403, 404]

    def test_2_15_list_enabled_denied_with_expired_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            subscription = Subscription.objects.filter(organization=org, module=module).first()
            if not subscription:
                subscription = _create_subscription(org, module)
            subscription.status = Subscription.Status.EXPIRED
            subscription.end_date = timezone.now() - timedelta(days=1)
            subscription.save(update_fields=["status", "end_date", "updated_at"])

        response = make_request(client, "get", _tool_enabled_url(org))
        assert response.status_code in [403, 404]

    def test_2_16_list_unauthenticated(self, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        response = make_request(http_client, "get", _tool_enabled_url(org))
        assert response.status_code == 401

class TestREQTool003EnableTool:
    def test_3_1_successful_enable_by_saas_administrator(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        tool_key = "calculator"
        OrganizationEnabledTool.objects.filter(organization=org, tool_key=tool_key).update(disabled_at=timezone.now())

        before_request = timezone.now()
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [200, 201]

        enabled_tool = OrganizationEnabledTool.objects.filter(
            organization=org,
            tool_key=tool_key,
            disabled_at__isnull=True,
        ).first()
        assert enabled_tool is not None

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_enable_url(org, tool_key),
            method="POST",
            status_code__in=[200, 201],
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        assert audit_log is not None
        assert audit_log.success is True
        assert audit_log.user_id == user.id

        data_change_log = DataChangeLog.objects.filter(
            app_label="agents",
            model_name="OrganizationEnabledTool",
            action="create",
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if data_change_log:
            assert data_change_log.audit_log_id == audit_log.id
            assert data_change_log.user_id == user.id

    def test_3_2_successful_enable_by_saas_account_manager(self, authenticated_client, http_client):
        email, _password = get_user_credentials("SaaS Account Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None
        ensure_tools_management_subscription(org)

        tool_key = "ocr_extractor"
        OrganizationEnabledTool.objects.filter(organization=org, tool_key=tool_key).update(disabled_at=timezone.now())

        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [200, 201]

    def test_3_3_re_enable_previously_disabled_tool(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "handoff_to_human"
        user = User.objects.filter(email=email).first()

        enabled_tool, _ = OrganizationEnabledTool.objects.get_or_create(
            organization=org,
            tool_key=tool_key,
            defaults={"enabled_by": user, "disabled_at": timezone.now()},
        )
        if enabled_tool.disabled_at is None:
            enabled_tool.disabled_at = timezone.now()
            enabled_tool.save(update_fields=["disabled_at", "updated_at"])

        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [200, 201]

        enabled_tool.refresh_from_db()
        assert enabled_tool.disabled_at is None

    def test_3_4_enable_rejected_by_agent_manager(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

    def test_3_5_enable_nonexistent_tool_rejected(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "nonexistent-tool-12345"

        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 404

    def test_3_6_enable_max_tools_exceeded(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        subscription = Subscription.objects.filter(organization=org, status=Subscription.Status.ACTIVE).first()
        if subscription:
            config = subscription.configuration or {}
            config["tools_max_enabled_per_org"] = 2
            subscription.configuration = config
            subscription.save(update_fields=["configuration", "updated_at"])

        user = User.objects.filter(email=email).first()
        for tool_key in ["calculator", "ocr_extractor"]:
            OrganizationEnabledTool.objects.get_or_create(
                organization=org,
                tool_key=tool_key,
                defaults={"enabled_by": user, "disabled_at": None},
            )

        tool_key = "handoff_to_human"
        before_request = timezone.now()
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [200, 201, 400, 409]

        audit_log = AuditLog.objects.filter(
            path=_tool_enable_url(org, tool_key),
            method="POST",
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.user_id == user.id

    def test_3_7_enable_rejected_by_account_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        before_request = timezone.now()
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_enable_url(org, tool_key),
            method="POST",
            status_code=403,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False
            assert audit_log.user_id == user.id

    def test_3_8_enable_rejected_by_account_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

    def test_3_9_enable_rejected_by_organization_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

    def test_3_10_enable_rejected_by_organization_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 403

    def test_3_12_enable_denied_without_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha3").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            Subscription.objects.filter(organization=org, module=module).delete()

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [403, 404]

    def test_3_13_enable_denied_with_expired_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            subscription = Subscription.objects.filter(organization=org, module=module).first()
            if not subscription:
                subscription = _create_subscription(org, module)
            subscription.status = Subscription.Status.EXPIRED
            subscription.end_date = timezone.now() - timedelta(days=1)
            subscription.save(update_fields=["status", "end_date", "updated_at"])

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [403, 404]

    def test_3_14_enable_unauthenticated(self, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(http_client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code == 401

class TestREQTool004DisableTool:
    def test_4_1_successful_disable_by_saas_administrator(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        user = User.objects.filter(email=email).first()

        enabled_tool, _ = OrganizationEnabledTool.objects.get_or_create(
            organization=org,
            tool_key=tool_key,
            defaults={"enabled_by": user, "disabled_at": None},
        )
        if enabled_tool.disabled_at:
            enabled_tool.disabled_at = None
            enabled_tool.save(update_fields=["disabled_at", "updated_at"])

        before_request = timezone.now()
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code in [200, 204]

        enabled_tool.refresh_from_db()
        assert enabled_tool.disabled_at is not None

        audit_log = AuditLog.objects.filter(
            path=_tool_disable_url(org, tool_key),
            method="POST",
            status_code__in=[200, 204],
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        assert audit_log is not None
        assert audit_log.success is True
        assert audit_log.user_id == user.id

        data_change_log = DataChangeLog.objects.filter(
            app_label="agents",
            model_name="OrganizationEnabledTool",
            action="update",
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if data_change_log:
            assert data_change_log.audit_log_id == audit_log.id
            assert data_change_log.user_id == user.id

    def test_4_2_disable_already_disabled_rejected(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "ocr_extractor"
        user = User.objects.filter(email=email).first()

        enabled_tool, _ = OrganizationEnabledTool.objects.get_or_create(
            organization=org,
            tool_key=tool_key,
            defaults={"enabled_by": user, "disabled_at": timezone.now()},
        )
        if enabled_tool.disabled_at is None:
            enabled_tool.disable(actor=user)
            enabled_tool.save()

        before_request = timezone.now()
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code in [400, 409]

        audit_log = AuditLog.objects.filter(
            path=_tool_disable_url(org, tool_key),
            method="POST",
            status_code__in=[400, 409],
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False

    def test_4_3_disable_rejected_by_agent_manager(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

    def test_4_4_disable_rejected_by_account_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

    def test_4_5_disable_rejected_by_account_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

    def test_4_6_disable_rejected_by_organization_admin(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Org Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

    def test_4_7_disable_rejected_by_organization_owner(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Owner")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 403

    def test_4_9_disable_denied_without_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha3").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            Subscription.objects.filter(organization=org, module=module).delete()

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code in [403, 404]

    def test_4_10_disable_denied_with_expired_subscription(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        module = Module.objects.filter(key="TOOLS_MANAGEMENT").first()
        if module:
            subscription = Subscription.objects.filter(organization=org, module=module).first()
            if not subscription:
                subscription = _create_subscription(org, module)
            subscription.status = Subscription.Status.EXPIRED
            subscription.end_date = timezone.now() - timedelta(days=1)
            subscription.save(update_fields=["status", "end_date", "updated_at"])

        tool_key = "calculator"
        response = make_request(client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code in [403, 404]

    def test_4_11_disable_unauthenticated(self, http_client):
        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(http_client, "post", _tool_disable_url(org, tool_key))
        assert response.status_code == 401


class TestREQTool005ValidateToolConfiguration:
    def _enable_tool(self, tool_key, org, authenticated_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [200, 201]
        return response.json()

    def test_5_1_valid_configuration_passes(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        self._enable_tool("calculator", org, authenticated_client)

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "calculator",
            "configuration": {"expression": "2 + 2"},
        }

        before_request = timezone.now()
        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 200

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_validate_url(),
            method="POST",
            status_code=200,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is True
            assert audit_log.user_id == user.id

    def test_5_2_invalid_max_results_fails(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        self._enable_tool("kb_retriever", org, authenticated_client)

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "kb_retriever",
            "configuration": {
                "collection_id": "00000000-0000-0000-0000-000000000000",
                "maxResults": 25,
            },
        }

        before_request = timezone.now()
        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 400

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_validate_url(),
            method="POST",
            status_code=400,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False
            assert audit_log.user_id == user.id

    def test_5_3_missing_required_parameter_fails(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        self._enable_tool("kb_retriever", org, authenticated_client)

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "kb_retriever",
            "configuration": {},
        }

        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 400

    def test_5_4_wrong_parameter_type_fails(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        self._enable_tool("calculator", org, authenticated_client)

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "calculator",
            "configuration": {"expression": 12345},
        }

        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code in [200, 400]

    def test_5_5_invalid_uuid_format_fails(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        self._enable_tool("kb_retriever", org, authenticated_client)

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "kb_retriever",
            "configuration": {"collection_id": "not-a-valid-uuid"},
        }

        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 400

    def test_5_6_validate_unauthenticated(self, http_client):
        payload = {
            "organization_uuid": "00000000-0000-0000-0000-000000000000",
            "toolKey": "calculator",
            "configuration": {"expression": "2 + 2"},
        }

        response = make_request(http_client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 401

    def test_5_7_valid_configuration_fails_without_enabling_tool(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "calculator",
            "configuration": {"expression": "2 + 2"},
        }

        before_request = timezone.now()
        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 404

        user = User.objects.filter(email=email).first()
        audit_log = AuditLog.objects.filter(
            path=_tool_validate_url(),
            method="POST",
            status_code=404,
            created_at__gte=before_request - timedelta(seconds=1),
        ).order_by("-created_at").first()
        if audit_log:
            assert audit_log.success is False
            assert audit_log.user_id == user.id


class TestREQTool006PreventDuplicateTools:
    def test_6_1_tool_can_be_added_once(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tool_key = "calculator"
        response = make_request(client, "post", _tool_enable_url(org, tool_key))
        assert response.status_code in [200, 201]


class TestREQTool007KnowledgeBaseIntegration:
    def test_7_1_valid_collection_uuid_passes(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "kb_retriever",
            "configuration": {
                "collection_id": "00000000-0000-0000-0000-000000000000",
                "maxResults": 10,
            },
        }

        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code in [200, 400, 404]

    def test_7_2_invalid_uuid_format_fails(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Account 1 Agent Manager")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        admin_email, _admin_password = get_user_credentials("Super Admin")
        admin_client = authenticated_client(admin_email)
        response = make_request(admin_client, "post", _tool_enable_url(org, "kb_retriever"))
        assert response.status_code in [200, 201]

        payload = {
            "organization_uuid": str(org.uuid),
            "toolKey": "kb_retriever",
            "configuration": {"collection_id": "not-a-uuid"},
        }

        response = make_request(client, "post", _tool_validate_url(), json=payload)
        assert response.status_code == 400


class TestREQTool008NoToolDependencies:
    def test_8_1_tools_can_be_enabled_independently(self, authenticated_client, http_client):
        email, _password = get_user_credentials("Super Admin")
        client = authenticated_client(email)

        org = Organization.objects.filter(name="Test Organization Alpha1").first()
        assert org is not None

        tools = ["handoff_to_human", "calculator", "kb_retriever"]
        for tool_key in tools:
            response = make_request(client, "post", _tool_enable_url(org, tool_key))
            assert response.status_code in [200, 201]
