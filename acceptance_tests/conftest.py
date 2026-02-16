"""
Pytest fixtures for acceptance tests.

These fixtures provide HTTP clients that can make real HTTP requests
to the API, either against a test server or a running instance.
"""
import os
import warnings
import pytest
import requests
import subprocess
import shutil
import platform
import time
from typing import Optional

# Suppress HTTPS warnings when SSL verification is disabled
if os.getenv("VERIFY_SSL", "false").lower() != "true":
    warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Django imports for database access
try:
    import django
    django.setup()
except:
    pass  # Django may already be configured

try:
    from django.db import connection, transaction, models, connections
    from django.db.models import Q
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from datetime import timedelta
    from apps.accounts.models import Account
    from apps.organizations.models import Organization
    from apps.users.models import User, UserOrganization
    from apps.common.models import AuditLog, DataChangeLog
    from apps.agents.models import OrganizationEnabledLLM, OrganizationEnabledTool
    from apps.authentication.models import AuthSession
    from apps.roles.models import Role, RoleAssignment
    from apps.subscriptions.models import Subscription
    from apps.products.models import Module, Product
    from apps.llms.models import LLMDefinition
    # LLMDefinition = None
    from apps.roles.constants import (
        ROLE_ACCOUNT_OWNER,
        ROLE_ACCOUNT_ADMINISTRATOR,
        ROLE_ORGANIZATION_OWNER,
        ROLE_ORGANIZATION_ADMINISTRATOR,
        ROLE_SAAS_ACCOUNT_MANAGER,
        ROLE_SAAS_ADMINISTRATOR,
        ROLE_AGENT_MANAGER,
    )
    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False
    Account = None
    Organization = None
    User = None
    UserOrganization = None
    AuditLog = None
    DataChangeLog = None
    OrganizationEnabledLLM = None
    OrganizationEnabledTool = None
    get_user_model = None
    Q = None
    connections = None
    Role = None
    RoleAssignment = None
    Subscription = None
    Module = None
    Product = None
    LLMDefinition = None
    ROLE_ACCOUNT_OWNER = None
    ROLE_ACCOUNT_ADMINISTRATOR = None
    ROLE_ORGANIZATION_OWNER = None
    ROLE_ORGANIZATION_ADMINISTRATOR = None
    ROLE_SAAS_ACCOUNT_MANAGER = None
    timezone = None
    timedelta = None

# Base URL for the API - can be overridden via environment variable
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
VERBOSE = os.getenv("VERBOSE", "true").lower() == "true"

# ============================================================================
# Test Data Definitions - Edit these to modify test data structure
# ============================================================================

# Account definitions
TEST_ACCOUNTS = [
    {
        "name": "Test Account Alpha",
        "contact_email": "alpha@test.com",
        "description": "Test account with multiple organizations",
    },
    {
        "name": "Test Account Beta",
        "contact_email": "beta@test.com",
        "description": "Test account with single organization",
    },
    {
        "name": "Test Account Gama",
        "contact_email": "gama@test.com",
        "description": "Test account without organizations",
    },
]

# Organization definitions
TEST_ORGANIZATIONS = [
    {
        "name": "Test Organization Alpha1",
        "account_name": "Test Account Alpha",
        "has_subscription": True,
    },
    {
        "name": "Test Organization Alpha2",
        "account_name": "Test Account Alpha",
        "has_subscription": True,
        "max_concurrent_sessions": 2,
    },
    {
        "name": "Test Organization Alpha3",
        "account_name": "Test Account Alpha",
        "has_subscription": False,
    },
    {
        "name": "Test Organization Beta1",
        "account_name": "Test Account Beta",
        "has_subscription": False,
    },
]

# User definitions
TEST_USERS = [
    # Account 1 users
    {
        "email": "account1.owner@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Owner",
        "account_name": "Test Account Alpha",
        "roles": {
            "account": ["Account Owner"],
            "organizations": {
                "Test Organization Alpha2": ["Organization Owner"],
            },
        },
        "memberships": ["Test Organization Alpha2"],
    },
    {
        "email": "account1.admin@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Admin",
        "account_name": "Test Account Alpha",
        "roles": {
            "account": ["Account Administrator"],
        },
        "memberships": [],
    },
    {
        "email": "account1.org.admin@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Org Admin",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha1": ["Organization Administrator"],
                "Test Organization Alpha3": ["Organization Administrator"],
            },
        },
        "memberships": ["Test Organization Alpha1", "Test Organization Alpha3"],
    },
    {
        "email": "account1.agent.manager@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Agent Manager",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha1": ["Agent Manager"],
            },
        },
        "memberships": ["Test Organization Alpha1"],
    },
    {
        "email": "account1.user.manager@test.com",
        "password": "Test123!",
        "full_name": "Account 1 User Manager",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha1": ["User Manager"],
            },
        },
        "memberships": ["Test Organization Alpha1"],
    },
    {
        "email": "account1.user.viewer@test.com",
        "password": "Test123!",
        "full_name": "Account 1 User Viewer",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha1": ["User Viewer"],
            },
        },
        "memberships": ["Test Organization Alpha1"],
    },
    {
        "email": "account1.user.admin@test.com",
        "password": "Test123!",
        "full_name": "Account 1 User Admin",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha1": ["User Admin"],
            },
        },
        "memberships": ["Test Organization Alpha1"],
    },
    {
        "email": "account1.team.manager@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Team Manager",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha2": ["Team Manager"],
            },
        },
        "memberships": ["Test Organization Alpha2"],
    },
    {
        "email": "account1.team.viewer@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Team Viewer",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha2": ["Team Viewer"],
            },
        },
        "memberships": ["Test Organization Alpha2"],
    },
    {
        "email": "account1.team.admin@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Team Admin",
        "account_name": "Test Account Alpha",
        "roles": {
            "organizations": {
                "Test Organization Alpha2": ["Team Admin"],
            },
        },
        "memberships": ["Test Organization Alpha2"],
    },
    {
        "email": "account1.user1@test.com",
        "password": "Test123!",
        "full_name": "Account 1 User 1",
        "account_name": "Test Account Alpha",
        "roles": {},
        "memberships": ["Test Organization Alpha1", "Test Organization Alpha3"],
    },
    {
        "email": "account1.user2@test.com",
        "password": "Test123!",
        "full_name": "Account 1 User 2",
        "account_name": "Test Account Alpha",
        "roles": {},
        "memberships": ["Test Organization Alpha2"],
    },
    {
        "email": "account1.user3@test.com",
        "password": "Test123!",
        "full_name": "Account 1 User 3",
        "account_name": "Test Account Alpha",
        "roles": {},
        "memberships": [],
    },
    {
        "email": "account1.inactive.user4@test.com",
        "password": "Test123!",
        "full_name": "Account 1 Inactive User 4",
        "account_name": "Test Account Alpha",
        "roles": {},
        "memberships": ["Test Organization Alpha2"],
        "is_active": False,
    },
    # Account 2 users
    {
        "email": "account2.owner@test.com",
        "password": "Test123!",
        "full_name": "Account 2 Owner",
        "account_name": "Test Account Beta",
        "roles": {
            "account": ["Account Owner"],
            "organizations": {
                "Test Organization Beta1": ["Organization Owner"],
            },
        },
        "memberships": ["Test Organization Beta1"],
    },
    {
        "email": "account2.user1@test.com",
        "password": "Test123!",
        "full_name": "Account 2 User 1",
        "account_name": "Test Account Beta",
        "roles": {},
        "memberships": ["Test Organization Beta1"],
    },
    # Account 4 users (Gama)
    {
        "email": "account4.owner@test.com",
        "password": "Test123!",
        "full_name": "Account 4 Owner",
        "account_name": "Test Account Gama",
        "roles": {
            "account": ["Account Owner"],
        },
        "memberships": [],
    },
    {
        "email": "account4.user1@test.com",
        "password": "Test123!",
        "full_name": "Account 4 User 1",
        "account_name": "Test Account Gama",
        "roles": {},
        "memberships": [],
    },
    # SAAS Account Manager
    {
        "email": "saas.account.manager@hudhud.ai",
        "password": "Manager123!",
        "full_name": "SaaS Account Manager",
        "account_name": None,  # Not tied to a specific account
        "is_staff": True,
        "roles": {
            "account": ["SaaS Account Manager"],
        },
        "memberships": [],
        "assigned_account_names": ["Test Account Alpha", "Test Account Gama"],  # Account 1 and 3
    },
]
NON_ADMIN_PERMISSIONS = [
    "user:create",
    "user:read",
    "user:update",
    "user:list",
    "user:manage_membership",
    "teams:create",
    "teams:read",
    "teams:update",
    "teams:delete",
    "teams:manage_members",
    "teams:deactivate",
    "teams:list",
    "roles:create",
    "roles:read",
    "roles:update",
    "roles:delete",
    "roles:assign",
    "roles:admin",
    "permissions:list",
    "files:upload",
    "files:read",
    "files:update",
    "files:delete",
    "files:admin",
    "files:public:read",
    "products:list",
    "products:read",
    "modules:list",
    "modules:read",
    "modules:config_schema",
    "subscriptions:read",
    "agents:create",
    "agents:read",
    "agents:update",
    "agents:delete",
    "agents:versions:save",
    "agents:versions:switch",
    "agents:clone",
    "agents:admin",
    "flows:create",
    "flows:read",
    "flows:update",
    "flows:delete",
    "flows:clone",
    "flows:versions:save",
    "flows:versions:switch",
    "flows:versions:read",
    "flows:publish",
    "flows:disable",
    "flows:enable",
    "flows:admin",
    "channels:create",
    "channels:read",
    "channels:update",
    "channels:activate",
    "channels:deactivate",
    "channels:delete",
    "channels:manage_grants",
    "channel:read_message",
    "channel:send_message",
    "channel:mark_read",
    "channel:send_template",
    "integrations:create",
    "integrations:read",
    "integrations:update",
    "integrations:activate",
    "integrations:deactivate",
    "integrations:delete",
    "integrations:test",
    "integrations:regenerate_secret",
    "kb:collections:create",
    "kb:collections:read",
    "kb:collections:update",
    "kb:collections:delete",
    "kb:resources:add",
    "kb:resources:remove",
    "kb:admin",
    "llms:read",
    "llms:validate",
    "tools:list",
    "tools:read",
]
ROLES_PERMISSIONS = {
    ROLE_ACCOUNT_OWNER: [
        "accounts:read",
        "accounts:update",
        "accounts:transfer-owner",
        "organizations:create",
        "organizations:read",
        "organizations:update",
        "organizations:delete",
        "accounts:assign-owner",
        "organizations:deactivate",
        "organizations:assign-owner",
        "organizations:list",
        "account_user:create",
        "account_user:read",
        "account_user:update",
        "account_user:delete",
        "account_user:list",
        "account_user:deactivate",
    ] + NON_ADMIN_PERMISSIONS,
    ROLE_ACCOUNT_ADMINISTRATOR: [
        "accounts:read",
        "accounts:update",
        "organizations:create",
        "organizations:read",
        "organizations:update",
        "organizations:delete",
        "organizations:deactivate",
        "organizations:assign-owner",
        "organizations:list",
        "account_user:create",
        "account_user:read",
        "account_user:update",
        "account_user:delete",
        "account_user:list",
        "account_user:deactivate",
    ] + NON_ADMIN_PERMISSIONS,
    ROLE_ORGANIZATION_OWNER: [
        "organizations:read",
        "organizations:update",
        "organizations:list",
        "organizations:transfer-owner",
    ] + NON_ADMIN_PERMISSIONS,
    ROLE_ORGANIZATION_ADMINISTRATOR: [
        "organizations:read",
        "organizations:update",
        "organizations:list",
    ] + NON_ADMIN_PERMISSIONS,
    ROLE_SAAS_ACCOUNT_MANAGER: [
        "accounts:read",
        "accounts:update",
        "accounts:list",
        "accounts:deactivate",
        "organizations:create",
        "organizations:read",
        "organizations:update",
        "organizations:delete",
        "organizations:deactivate",
        "organizations:list",
        "organizations:transfer-owner",
        "organizations:assign-owner",
        "account_user:create",
        "account_user:read",
        "account_user:update",
        "account_user:delete",
        "account_user:list",
        "account_user:deactivate",
        "teams:view_all",
        "subscriptions:create",
        "subscriptions:update",
        "subscriptions:delete",
        "subscriptions:admin",
        "llms:list",
        "llms:enable",
        "llms:disable",
        "llms:admin",
        "tools:enable",
        "tools:disable",
        "tools:admin",
    ] + NON_ADMIN_PERMISSIONS,
    ROLE_SAAS_ADMINISTRATOR: [
        "accounts:create",
        "accounts:read",
        "accounts:update",
        "accounts:delete",
        "accounts:list",
        "accounts:deactivate",
        "accounts:transfer-owner",
        "organizations:create",
        "organizations:read",
        "organizations:update",
        "organizations:delete",
        "organizations:deactivate",
        "organizations:list",
        "organizations:transfer-owner",
        "account_user:create",
        "account_user:read",
        "account_user:update",
        "account_user:delete",
        "account_user:list",
        "account_user:deactivate",
        "teams:view_all",
        "subscriptions:create",
        "subscriptions:update",
        "subscriptions:delete",
        "subscriptions:admin",
        "llms:list",
        "llms:enable",
        "llms:disable",
        "llms:admin",
        "tools:enable",
        "tools:disable",
        "tools:admin",
    ] + NON_ADMIN_PERMISSIONS,
    ROLE_AGENT_MANAGER: [
            "agents:create", "agents:read", "agents:update", "agents:delete",
            "agents:versions:save", "agents:versions:switch", "agents:clone",
            "agents:flows:create", "agents:flows:read", "agents:flows:update",
            "agents:flows:delete", "agents:flows:publish", "agents:flows:disable",
            "agents:flows:enable", "agents:flows:clone", "agents:flows:versions:read",
            "integrations:create", "integrations:read", "integrations:update",
            "integrations:activate", "integrations:deactivate", "integrations:delete",
            "integrations:test", "integrations:regenerate_secret",
            "llms:read", "llms:validate",
            "kb:collections:create", "kb:collections:read", "kb:collections:update",
            "kb:collections:delete", "kb:collections:archive", "kb:collections:restore",
            "kb:resources:create", "kb:resources:delete", "kb:resources:move",
            "kb:resources:copy", "tools:read"
        ],
    # Predefined user management roles
    "User Manager": ["user:create", "user:read", "user:update", "user:list"],
    "User Viewer": ["user:read", "user:list"],
    "User Admin": ["user:create", "user:read", "user:update", "user:list", "user:manage_membership"],
    # Predefined team management roles
    "Team Manager": ["teams:create", "teams:read", "teams:update", "teams:manage_members"],
    "Team Viewer": ["teams:read", "teams:list"],
    "Team Admin": [
        "teams:create", "teams:read", "teams:update", "teams:delete",
        "teams:deactivate", "teams:manage_members",
    ],
}

# Predefined user management role names (for seeding, same as keys in ROLES_PERMISSIONS above)
PREDEFINED_USER_ROLE_NAMES = ["User Manager", "User Viewer", "User Admin"]
# Predefined team management role names
PREDEFINED_TEAM_ROLE_NAMES = ["Team Manager", "Team Viewer", "Team Admin"]


def get_user_credentials(full_name: str) -> tuple[str, str]:
    """
    Get user credentials (email, password) by full_name.
    
    This is a single point of truth for test user credentials.
    All tests should use this function instead of hardcoding credentials.
    
    Args:
        full_name: The full_name of the user from TEST_USERS
        
    Returns:
        Tuple of (email, password)
        
    Raises:
        ValueError: If user with given full_name is not found in TEST_USERS
    """
    if full_name == "Super Admin":
        return "admin@hudhud.ai", "admin123"
    for user in TEST_USERS:
        if user.get("full_name") == full_name:
            return user["email"], user["password"]
    
    raise ValueError(f"User with full_name '{full_name}' not found in TEST_USERS")


# Tables to truncate in order (respecting foreign key constraints)
# Add or remove tables here as needed
# Note: User table is handled separately to preserve superuser
# This list will be filtered to only include available models
def get_truncate_tables():
    """Get list of tables to truncate, filtering out None models."""
    return [model for model in [
        DataChangeLog,
        AuditLog,
        OrganizationEnabledLLM,
        OrganizationEnabledTool,
        LLMDefinition,
        RoleAssignment,
        Role,
        Subscription,
        AuthSession,
        UserOrganization,
        Organization,
        Account,
        User,
        # User is handled separately to preserve superuser
    ] if model is not None]

# Configure pytest-django for acceptance tests
# Acceptance tests use the real database, not a test database
def pytest_configure(config):
    """Configure pytest-django to use the real database for acceptance tests."""
    # For acceptance tests, we want to use the same database as the API server
    # Prevent pytest-django from creating a test database
    import django
    from django.conf import settings
    
    # Get the real database name from environment or settings
    db_name = os.getenv('DB_NAME') or settings.DATABASES['default']['NAME']
    
    # CRITICAL: Set the database name to the real database name BEFORE pytest-django processes it
    # This prevents pytest-django from creating test_{db_name}
    settings.DATABASES['default']['NAME'] = db_name
    
    # Force pytest-django to use this exact database name (no test_ prefix)
    # Set reuse_db to prevent database creation/deletion
    if hasattr(config.option, 'reuse_db'):
        config.option.reuse_db = True
    
    # CRITICAL: Set environment variable to tell pytest-django to use this database name
    # This prevents pytest-django from adding the test_ prefix
    os.environ['DJANGO_DB_NAME'] = db_name
    
    # Also try to set it as a config option if available
    if hasattr(config.option, 'django_db_name'):
        config.option.django_db_name = db_name
    
    # Disable test database creation by setting this flag
    # This is the most reliable way to prevent test database creation
    if hasattr(config.option, 'create_db'):
        config.option.create_db = False

def pytest_collection_modifyitems(config, items):
    """Automatically add django_db marker to all acceptance tests."""
    for item in items:
        # Add django_db marker to all acceptance tests
        # Use transaction=True to allow commits (needed for truncation)
        # Use databases=['default'] to explicitly use the default (real) database
        if "acceptance" in item.keywords:
            item.add_marker(pytest.mark.django_db(transaction=True, databases=['default']))

# Configure pytest-django to allow database access for acceptance tests
# This is needed because acceptance tests use the real database, not a test database
pytest_plugins = ['pytest_django']

@pytest.fixture(scope='session')
def django_db_setup(django_db_blocker, request):
    """
    Override pytest-django's database setup to use the real database.
    
    This prevents pytest-django from creating a test database with test_ prefix.
    We use the real database that the API server uses.
    """
    from django.conf import settings
    from django.db import connections
    
    # Get the real database name from environment
    db_name = os.getenv('DB_NAME')
    if not db_name:
        # Fallback to settings, but remove test_ prefix if present
        db_name = settings.DATABASES['default']['NAME']
        if db_name.startswith('test_'):
            db_name = db_name[5:]  # Remove 'test_' prefix
    
    # CRITICAL: Force the database name to the real database BEFORE any setup
    settings.DATABASES['default']['NAME'] = db_name
    
    # Update all connection settings
    if 'default' in connections:
        connections['default'].settings_dict['NAME'] = db_name
    
    # Yield without doing any database setup/teardown
    # The database should already exist and be used by the API server
    # We use django_db_blocker to allow database access but don't create anything
    with django_db_blocker.unblock():
        # Just ensure connection is established, don't create database
        try:
            connections['default'].ensure_connection()
        except Exception:
            pass
    
    yield
    
    # No teardown - we don't want to delete the real database

@pytest.fixture(scope='function', autouse=True)
def fix_database_name_after_pytest_django():
    """
    Fix database name after pytest-django modifies it.
    
    This runs before each test to ensure the database name is correct
    even if pytest-django modified it during setup.
    """
    from django.conf import settings
    from django.db import connections
    
    # Get the real database name from environment
    db_name = os.getenv('DB_NAME')
    if not db_name:
        # Fallback to settings, but remove test_ prefix if present
        current_name = settings.DATABASES['default']['NAME']
        if current_name.startswith('test_'):
            db_name = current_name[5:]  # Remove 'test_' prefix
        else:
            db_name = current_name
    
    # CRITICAL: Force the database name to the real database
    # This must be done AFTER pytest-django's setup runs
    if settings.DATABASES['default']['NAME'] != db_name:
        settings.DATABASES['default']['NAME'] = db_name
        
        # Update all connection settings
        if 'default' in connections:
            connections['default'].settings_dict['NAME'] = db_name
            # Close and reconnect to ensure we're using the correct database
            try:
                connections['default'].close()
            except Exception:
                pass
    
    yield
    
    # No cleanup needed

@pytest.fixture(scope="session")
def api_base_url() -> str:
    """
    Base URL for API requests.
    
    Can be set via API_BASE_URL environment variable.
    Defaults to http://localhost:8000/api for local development.
    """
    return API_BASE_URL


@pytest.fixture
def http_client(api_base_url: str):
    """
    Basic HTTP client (unauthenticated).
    
    Returns a requests.Session configured with the base URL.
    Handles SSL verification based on VERIFY_SSL environment variable.
    """
    session = requests.Session()
    session.base_url = api_base_url
    
    # Disable SSL verification for self-signed certificates (common in local/dev)
    # Set VERIFY_SSL=true to enable verification
    verify_ssl = os.getenv("VERIFY_SSL", "false").lower() == "true"
    session.verify = verify_ssl
    
    return session


@pytest.fixture
def authenticated_client(http_client, api_base_url: str):
    """
    Authenticated HTTP client factory.
    
    Usage:
        client = authenticated_client(username="user@example.com", password="pass")
    """
    def _get_client(username: str, password: str) -> requests.Session:
        """Get authenticated client with JWT tokens."""
        # Obtain JWT token
        token_url = f"{api_base_url.replace('/api', '')}/api/auth/token/"
        verify_ssl = os.getenv("VERIFY_SSL", "false").lower() == "true"
        response = http_client.post(
            token_url,
            json={"email": username, "password": password},
            verify=verify_ssl,
        )
        response.raise_for_status()
        tokens = response.json()
        
        # Configure session with access token
        client = requests.Session()
        client.verify = verify_ssl
        client.base_url = api_base_url
        client.refresh_token = tokens['refresh']
        client.access_token = tokens['access']
        client.headers.update({
            "Authorization": f"Bearer {tokens['access']}",
            "Content-Type": "application/json",
        })
        return client
    
    return _get_client


@pytest.fixture
def admin_client(authenticated_client, api_base_url: str):
    """
    Pre-authenticated admin/superuser client.
    
    Uses the superuser created during test data seeding.
    Requires ADMIN_EMAIL and ADMIN_PASSWORD environment variables,
    or uses defaults for test environment.
    """
    admin_email = os.getenv("ADMIN_EMAIL", "admin@hudhud.ai")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    return authenticated_client(admin_email, admin_password)


@pytest.fixture
def manager_client(authenticated_client, api_base_url: str):
    """
    Pre-authenticated SaaS Account Manager client.
    
    Uses the SAAS Account Manager from TEST_USERS.
    Can be overridden with MANAGER_EMAIL and MANAGER_PASSWORD environment variables.
    """
    manager_email = os.getenv("MANAGER_EMAIL", "saas.account.manager@hudhud.ai")
    manager_password = os.getenv("MANAGER_PASSWORD", "Manager123!")
    
    return authenticated_client(manager_email, manager_password)


@pytest.fixture
def regular_client(authenticated_client, api_base_url: str):
    """
    Pre-authenticated regular user client.
    
    Uses a regular user from TEST_USERS (account1.user1@test.com).
    Can be overridden with USER_EMAIL and USER_PASSWORD environment variables.
    """
    user_email = os.getenv("USER_EMAIL", "account1.user1@test.com")
    user_password = os.getenv("USER_PASSWORD", "Test123!")
    
    return authenticated_client(user_email, user_password)


@pytest.fixture(scope="session")
def test_server_available(api_base_url: str) -> bool:
    """
    Check if test server is available.
    
    Skips tests if server is not reachable.
    """
    try:
        # Try to reach the health endpoint or base URL
        health_url = api_base_url.replace("/api", "") + "/api/schema/"
        
        # Disable SSL verification for self-signed certificates (common in local/dev)
        # This allows HTTPS connections to work with self-signed certs
        verify_ssl = os.getenv("VERIFY_SSL", "false").lower() == "true"
        
        response = requests.get(health_url, timeout=5, verify=verify_ssl)
        return response.status_code in (200, 401, 403)  # Any response means server is up
    except requests.exceptions.SSLError:
        # SSL error - try again with verification disabled
        try:
            health_url = api_base_url.replace("/api", "") + "/api/schema/"
            response = requests.get(health_url, timeout=5, verify=False)
            return response.status_code in (200, 401, 403)
        except requests.exceptions.RequestException:
            return False
    except requests.exceptions.RequestException:
        return False


@pytest.fixture(autouse=True)
def require_test_server(test_server_available, request):
    """
    Auto-skip acceptance tests if server is not available.
    
    Can be overridden with pytest.mark.no_server_check
    """
    if not test_server_available and "no_server_check" not in request.keywords:
        pytest.skip("Test server not available. Start server or set API_BASE_URL.")


def create_static_data(superuser: User):
    """
    Create static data after truncation.
    Creates products and modules based on the business requirements specification.
    """
    if not DJANGO_AVAILABLE:
        return
    
    if VERBOSE:
        print("CREATING STATIC DATA")
    
    # Define products from JSON specification
    products_data = [
        {
            "key": "AGENTS_PLATFORM",
            "name": "Agents Platform",
            "description": "AI-powered customer service platform with intelligent agents",
            "target_segments": ["Customer Service", "Support Teams", "Sales Teams"],
            "use_cases": [
                "Automated customer support",
                "Lead qualification",
                "Knowledge base management",
                "Multi-channel communication"
            ],
            "availableModuleKeys": [
                "USER_MANAGEMENT", "ROLE_AND_PERMISSION_MANAGEMENT", "TEAMS_MANAGEMENT",
                "FILES_MANAGEMENT", "AGENTS_MANAGEMENT", "CHANNELS_MANAGEMENT",
                "FLOWS_MANAGEMENT", "INTEGRATIONS_MANAGEMENT", "KNOWLEDGE_BASE_MANAGEMENT",
                "LLM_MANAGEMENT", "TOOLS_MANAGEMENT"
            ]
        },
        {
            "key": "ONE_INBOX",
            "name": "One Inbox",
            "description": "Unified communication hub for managing all customer interactions",
            "target_segments": ["Customer Service", "Support Teams", "Sales Teams"],
            "use_cases": [
                "Centralized message management",
                "Multi-channel support",
                "Team collaboration",
                "Workflow automation"
            ],
            "availableModuleKeys": [
                "USER_MANAGEMENT", "ROLE_AND_PERMISSION_MANAGEMENT", "TEAMS_MANAGEMENT",
                "FILES_MANAGEMENT", "CHANNELS_MANAGEMENT"
            ]
        },
        {
            "key": "DOCVERSE",
            "name": "DocVerse",
            "description": "Document management and collaboration platform",
            "target_segments": ["Content Teams", "Knowledge Workers", "Documentation Teams"],
            "use_cases": [
                "Document collaboration",
                "Knowledge management",
                "Content creation",
                "Document workflows"
            ],
            "availableModuleKeys": [
                "USER_MANAGEMENT", "ROLE_AND_PERMISSION_MANAGEMENT", "TEAMS_MANAGEMENT",
                "FILES_MANAGEMENT", "KNOWLEDGE_BASE_MANAGEMENT"
            ]
        }
    ]
    
    # Define subscribable modules from JSON specification
    subscribable_modules_data = [
        {
            "key": "USER_MANAGEMENT",
            "code": "UM",
            "name": "User Management",
            "description": "Comprehensive user lifecycle management with organization membership and role assignment",
            "subscribable": True,
            "configurable_attributes": {
                "max_users_per_org": {"type": "integer", "required": True, "min": 1, "max": 10000, "default": 10},
                "max_orgs_per_user": {"type": "integer", "required": True, "min": 1, "max": 100, "default": 5},
                "user_retention_days": {"type": "integer", "required": True, "min": 30, "max": 2555, "default": 365}
            },
            "exposed_permissions": [
                "user:create", "user:read", "user:update", "user:delete", "user:list",
                "user:deactivate", "user:suspend", "user:manage_membership", "user:view_all",
                "account_user:create", "account_users:read", "account_users:update",
                "account_users:delete", "account_users:list", "account_user:deactivate"
            ]
        },
        {
            "key": "TEAMS_MANAGEMENT",
            "code": "TM",
            "name": "Team Management",
            "description": "Team creation, member management, and team-based collaboration features",
            "subscribable": True,
            "configurable_attributes": {
                "max_teams": {"type": "integer", "required": True, "min": 1, "max": 1000, "default": 5},
                "max_team_members": {"type": "integer", "required": True, "min": 1, "max": 1000, "default": 50},
                "team_retention_days": {"type": "integer", "required": True, "min": 30, "max": 365, "default": 90}
            },
            "exposed_permissions": [
                "teams:create", "teams:read", "teams:update", "teams:delete",
                "teams:manage_members", "teams:deactivate", "teams:list", "teams:view_all"
            ]
        },
        {
            "key": "ROLE_AND_PERMISSION_MANAGEMENT",
            "code": "RPM",
            "name": "Role & Permission Management",
            "description": "Custom role creation, permission assignment, and access control management",
            "subscribable": True,
            "configurable_attributes": {
                "max_custom_roles_per_org": {"type": "integer", "required": True, "min": 5, "max": 100, "default": 10},
                "max_permissions_per_role": {"type": "integer", "required": True, "min": 10, "max": 200, "default": 50},
                "max_role_assignments_per_user": {"type": "integer", "required": True, "min": 1, "max": 20, "default": 5},
                "role_assignment_audit_retention_days": {"type": "integer", "required": True, "min": 90, "max": 2555, "default": 365}
            },
            "exposed_permissions": [
                "roles:create", "roles:read", "roles:update", "roles:delete",
                "roles:assign", "roles:admin", "permissions:list"
            ]
        },
        {
            "key": "FILES_MANAGEMENT",
            "code": "FM",
            "name": "Files Management",
            "description": "Secure file storage, organization, and access control with versioning",
            "subscribable": True,
            "configurable_attributes": {
                "max_file_size": {"type": "integer", "required": True, "min": 1048576, "max": 104857600, "default": 10485760},
                "max_storage_quota": {"type": "integer", "required": True, "min": 1073741824, "max": 1099511627776, "default": 10737418240},
                "max_files_per_user": {"type": "integer", "required": True, "min": 100, "max": 10000, "default": 1000},
                "file_retention_days": {"type": "integer", "required": True, "min": 30, "max": 365, "default": 90},
                "version_history_limit": {"type": "integer", "required": True, "min": 1, "max": 50, "default": 10}
            },
            "exposed_permissions": [
                "files:upload", "files:read", "files:update", "files:delete",
                "files:admin", "files:public:read"
            ]
        },
        {
            "key": "AGENTS_MANAGEMENT",
            "code": "AGM",
            "name": "Agent Management",
            "description": "AI agent creation, configuration, and management with LLM and tools integration",
            "subscribable": True,
            "configurable_attributes": {
                "agents_max_agents_per_org": {"type": "integer", "required": True, "min": 1, "max": 1000, "default": 10},
                "agents_enabled_hosted_llms": {"type": "array", "required": False, "default": []},
                "agents_tool_invocations_per_month": {"type": "integer", "required": True, "min": 0, "max": None, "default": 1000}
            },
            "exposed_permissions": [
                "agents:create", "agents:read", "agents:update", "agents:delete",
                "agents:versions:save", "agents:versions:switch", "agents:clone",
                "agents:llms:enable", "agents:tools:enable", "agents:admin"
            ]
        },
        {
            "key": "CHANNELS_MANAGEMENT",
            "code": "CM",
            "name": "Channels Management",
            "description": "Multi-channel communication configuration for Web Chat, WhatsApp, and X/Twitter",
            "subscribable": True,
            "configurable_attributes": {
                "enabledChannelTypes.web_chat.enabled": {"type": "boolean", "required": True, "default": True},
                "enabledChannelTypes.web_chat.maxInstances": {"type": "integer", "required": True, "min": 1, "max": 100, "default": 1},
                "enabledChannelTypes.whatsapp.enabled": {"type": "boolean", "required": True, "default": False},
                "enabledChannelTypes.whatsapp.maxInstances": {"type": "integer", "required": True, "min": 1, "max": 50, "default": 1},
                "enabledChannelTypes.x.enabled": {"type": "boolean", "required": True, "default": False},
                "enabledChannelTypes.x.maxInstances": {"type": "integer", "required": True, "min": 1, "max": 10, "default": 1}
            },
            "exposed_permissions": [
                "channels:create", "channels:read", "channels:update", "channels:activate",
                "channels:deactivate", "channels:delete", "channels:manage_grants",
                "channel:read_message", "channel:send_message", "channel:mark_read", "channel:send_template"
            ]
        },
        {
            "key": "FLOWS_MANAGEMENT",
            "code": "FLM",
            "name": "Flows Management",
            "description": "Visual workflow builder with versioning and state management",
            "subscribable": True,
            "configurable_attributes": {
                "flows_max_flows_per_org": {"type": "integer", "required": True, "min": 1, "max": 10000, "default": 10}
            },
            "exposed_permissions": [
                "flows:create", "flows:read", "flows:update", "flows:delete", "flows:clone",
                "flows:versions:save", "flows:versions:switch", "flows:versions:read",
                "flows:publish", "flows:disable", "flows:enable", "flows:admin"
            ]
        },
        {
            "key": "INTEGRATIONS_MANAGEMENT",
            "code": "IM",
            "name": "Integrations Management",
            "description": "External system communication via REST APIs and webhooks",
            "subscribable": True,
            "configurable_attributes": {
                "integrations.api.enabled": {"type": "boolean", "required": True, "default": False},
                "integrations.api.maxInstances": {"type": "integer", "required": True, "min": 1, "max": 1000, "default": 10},
                "integrations.api.maxInvocationsPerMonth": {"type": "integer", "required": True, "min": 0, "max": None, "default": 10000},
                "integrations.webhook.enabled": {"type": "boolean", "required": True, "default": False},
                "integrations.webhook.maxInstances": {"type": "integer", "required": True, "min": 1, "max": 1000, "default": 5},
                "integrations.webhook.maxInvocationsPerMonth": {"type": "integer", "required": True, "min": 0, "max": None, "default": 5000}
            },
            "exposed_permissions": [
                "integrations:create", "integrations:read", "integrations:update",
                "integrations:activate", "integrations:deactivate", "integrations:delete",
                "integrations:test", "integrations:regenerate_secret"
            ]
        },
        {
            "key": "KNOWLEDGE_BASE_MANAGEMENT",
            "code": "KBM",
            "name": "Knowledge Base Management",
            "description": "Knowledge collections and resources for document organization and retrieval",
            "subscribable": True,
            "configurable_attributes": {
                "kb_max_collections_per_org": {"type": "integer", "required": True, "min": 1, "max": 100, "default": 3},
                "kb_max_resources_per_collection": {"type": "integer", "required": True, "min": 1, "max": 1000, "default": 10},
                "kb_max_resource_file_size": {"type": "integer", "required": True, "min": 1, "max": 52428800, "default": 52428800}
            },
            "exposed_permissions": [
                "kb:collections:create", "kb:collections:read", "kb:collections:update",
                "kb:collections:delete", "kb:resources:add", "kb:resources:remove", "kb:admin"
            ]
        },
        {
            "key": "LLM_MANAGEMENT",
            "code": "LM",
            "name": "LLM Management",
            "description": "Large Language Model discovery, enablement, and configuration management",
            "subscribable": True,
            "configurable_attributes": {
                "llms_enabled_hosted_models": {"type": "array", "required": False, "default": []},
                "llms_max_enabled_per_org": {"type": "integer", "required": True, "min": 1, "max": 100, "default": 20}
            },
            "exposed_permissions": [
                "llms:list", "llms:read", "llms:enable", "llms:disable", "llms:admin"
            ]
        },
        {
            "key": "TOOLS_MANAGEMENT",
            "code": "TLM",
            "name": "Tools Management",
            "description": "Agent tool discovery, enablement, and configuration management",
            "subscribable": True,
            "configurable_attributes": {
                "tools_invocations_per_month": {"type": "integer", "required": True, "min": 0, "max": None, "default": 1000},
                "tools_max_enabled_per_org": {"type": "integer", "required": True, "min": 0, "max": 100, "default": 50}
            },
            "exposed_permissions": [
                "tools:list", "tools:read", "tools:enable", "tools:disable", "tools:admin"
            ]
        }
    ]
    
    # Define non-subscribable modules from JSON specification
    non_subscribable_modules_data = [
        {
            "key": "ACCOUNT_MANAGEMENT",
            "code": "AM",
            "name": "Account Management",
            "description": "Enterprise account lifecycle management and administration",
            "subscribable": False,
            "configurable_attributes": None,
            "exposed_permissions": [
                "accounts:create", "accounts:read", "accounts:update", "accounts:delete",
                "accounts:list", "accounts:deactivate", "accounts:transfer_owner"
            ]
        },
        {
            "key": "ORGANIZATION_MANAGEMENT",
            "code": "OM",
            "name": "Organization Management",
            "description": "Organization lifecycle management within enterprise accounts",
            "subscribable": False,
            "configurable_attributes": None,
            "exposed_permissions": [
                "organizations:create", "organizations:read", "organizations:update",
                "organizations:delete", "organizations:list", "organizations:deactivate",
                "organizations:assign_owner", "organizations:transfer_owner"
            ]
        },
        {
            "key": "AUTHENTICATION_AND_AUTHORIZATION",
            "code": "AA",
            "name": "Authentication & Authorization",
            "description": "User authentication, session management, and authorization services",
            "subscribable": False,
            "configurable_attributes": None,
            "exposed_permissions": [
                "auth:login", "auth:logout", "auth:refresh", "auth:context_switch",
                "auth:password_reset", "auth:sessions_list", "authz:permission_check",
                "authz:resource_access"
            ]
        },
        {
            "key": "SUBSCRIPTION_MANAGEMENT",
            "code": "SM",
            "name": "Subscription Management",
            "description": "Module subscription management with configurable attributes and permission control",
            "subscribable": False,
            "configurable_attributes": None,
            "exposed_permissions": [
                "subscriptions:create", "subscriptions:read", "subscriptions:update",
                "subscriptions:delete", "subscriptions:admin"
            ]
        }
    ]
    
    # Create products
    created_products = {}
    for product_data in products_data:
        product, _ = Product.objects.using('default').get_or_create(
            key=product_data["key"],
            defaults={
                "name": product_data["name"],
                "description": product_data["description"],
                "target_segments": product_data["target_segments"],
                "use_cases": product_data["use_cases"],
                "is_active": True
            }
        )
        created_products[product_data["key"]] = product
    
    # Create subscribable modules
    created_modules = {}
    for module_data in subscribable_modules_data:
        module, _ = Module.objects.using('default').get_or_create(
            key=module_data["key"],
            defaults={
                "code": module_data["code"],
                "name": module_data["name"],
                "description": module_data["description"],
                "subscribable": module_data["subscribable"],
                "configurable_attributes": module_data["configurable_attributes"],
                "exposed_permissions": module_data["exposed_permissions"],
                "is_active": True
            }
        )
        created_modules[module_data["key"]] = module
    
    # Create non-subscribable modules
    for module_data in non_subscribable_modules_data:
        module, _ = Module.objects.using('default').get_or_create(
            key=module_data["key"],
            defaults={
                "code": module_data["code"],
                "name": module_data["name"],
                "description": module_data["description"],
                "subscribable": module_data["subscribable"],
                "configurable_attributes": module_data["configurable_attributes"],
                "exposed_permissions": module_data["exposed_permissions"],
                "is_active": True
            }
        )
        created_modules[module_data["key"]] = module
    
    # Link modules to products (many-to-many relationship)
    
    for product_data in products_data:
        product = created_products[product_data["key"]]
        for product_module_key in product_data["availableModuleKeys"]:
            if product_module_key in created_modules:
                module = created_modules[product_module_key]
                # Use add() which handles duplicates automatically
                module.products.add(product)
            else:
                if VERBOSE:
                    print(f"Warning: Module key '{product_module_key}' (from product reference '{product_module_key}') not found for product '{product_data['key']}'")
    
    # Create LLM definitions from JSON specification
    # Note: Tools are loaded dynamically from JSON files, so they don't need to be seeded here
    llms_data = [
        {
            "modelProvider": "OpenAI",
            "modelKey": "gpt-4o-mini",
            "displayName": "GPT-4o Mini",
            "description": "GPT-4o Mini is a small, fast, and powerful model that is perfect for most use cases.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 1000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 1000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}},
                "seed": {"type": "number", "default": 42, "required": False, "description": "The seed of the model.", "validation": {"min": 0, "max": 1000000}}
            }
        },
        {
            "modelProvider": "OpenAI",
            "modelKey": "gpt-4",
            "displayName": "GPT-4",
            "description": "GPT-4 is a strong general-purpose model.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}},
                "seed": {"type": "number", "default": 42, "required": False, "description": "The seed of the model.", "validation": {"min": 0, "max": 1000000}}
            }
        },
        {
            "modelProvider": "OpenAI",
            "modelKey": "gpt-4",
            "displayName": "GPT-4",
            "description": "GPT-4 is a strong general-purpose model.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}},
                "seed": {"type": "number", "default": 42, "required": False, "description": "The seed of the model.", "validation": {"min": 0, "max": 1000000}}
            }
        },
        {
            "modelProvider": "OpenAI",
            "modelKey": "gpt-5",
            "displayName": "GPT-5",
            "description": "GPT-5 is the next generation of OpenAI's flagship language model with breakthrough capabilities.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 2000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 2000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}},
                "seed": {"type": "number", "default": 42, "required": False, "description": "The seed of the model.", "validation": {"min": 0, "max": 1000000}}
            }
        },
        {
            "modelProvider": "OpenAI",
            "modelKey": "gpt-5-mini",
            "displayName": "GPT-5 Mini",
            "description": "GPT-5 Mini is a smaller, faster, and more efficient version of GPT-5.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 1000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 1000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}},
                "seed": {"type": "number", "default": 42, "required": False, "description": "The seed of the model.", "validation": {"min": 0, "max": 1000000}}
            }
        },
        {
            "modelProvider": "Google",
            "modelKey": "gemini-2.5-pro",
            "displayName": "Gemini 2.5 Pro",
            "description": "Gemini 2.5 Pro is Google's most capable multimodal AI model with advanced reasoning.",
            "supportedModalities": ["text", "image", "audio", "video"],
            "maxContextTokens": 2000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 2000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Google",
            "modelKey": "gemini-2.5-flash",
            "displayName": "Gemini 2.5 Flash",
            "description": "Gemini 2.5 Flash is a fast and efficient multimodal model optimized for speed and performance.",
            "supportedModalities": ["text", "image", "audio", "video"],
            "maxContextTokens": 1000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 1000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Anthropic",
            "modelKey": "claude-sonnet-4.5",
            "displayName": "Claude Sonnet 4.5",
            "description": "Claude Sonnet 4.5 is Anthropic's most advanced model with exceptional reasoning and analytical capabilities.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 2000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 2000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Anthropic",
            "modelKey": "claude-sonnet-4",
            "displayName": "Claude Sonnet 4",
            "description": "Claude Sonnet 4 is a powerful model with strong reasoning and analytical capabilities.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 1000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 1000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "deepseek-v3-0324",
            "displayName": "DeepSeek V3 0324",
            "description": "DeepSeek V3 0324 is a large-scale model with advanced capabilities hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "deepseek-r1",
            "displayName": "DeepSeek R1",
            "description": "DeepSeek R1 is a large, powerful, and accurate model hosted by Hudhud.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 1000000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 1000000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "frequencyPenalty": {"type": "number", "default": 0, "required": False, "description": "The frequency penalty of the model.", "validation": {"min": 0, "max": 1}},
                "presencePenalty": {"type": "number", "default": 0, "required": False, "description": "The presence penalty of the model.", "validation": {"min": 0, "max": 1}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}},
                "seed": {"type": "number", "default": 42, "required": False, "description": "The seed of the model.", "validation": {"min": 0, "max": 1000000}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "qwen3-8b",
            "displayName": "Qwen3 8B",
            "description": "Qwen3 8B is a medium-sized efficient model hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "qwen3-14b",
            "displayName": "Qwen3 14B",
            "description": "Qwen3 14B is a balanced model with good performance hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "qwen3-32b",
            "displayName": "Qwen3 32B",
            "description": "Qwen3 32B is a large model with strong capabilities hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "qwen3-vl-8b",
            "displayName": "Qwen3 VL 8B",
            "description": "Qwen3 VL 8B is a vision-language model with multimodal capabilities hosted by Hudhud.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "qwen3-vl-32b",
            "displayName": "Qwen3 VL 32B",
            "description": "Qwen3 VL 32B is a large vision-language model with advanced multimodal capabilities hosted by Hudhud.",
            "supportedModalities": ["text", "image"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "gemma3-4b",
            "displayName": "Gemma3 4B",
            "description": "Gemma3 4B is a small, efficient model hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "gemma3-12b",
            "displayName": "Gemma3 12B",
            "description": "Gemma3 12B is a medium-sized balanced model hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        },
        {
            "modelProvider": "Hudhud Hosted",
            "modelKey": "gemma3-27b",
            "displayName": "Gemma3 27B",
            "description": "Gemma3 27B is a large model with strong capabilities hosted by Hudhud.",
            "supportedModalities": ["text"],
            "maxContextTokens": 128000,
            "modelConfiguration": {
                "temperature": {"type": "number", "default": 0.5, "required": False, "description": "The temperature of the model.", "validation": {"min": 0, "max": 1}},
                "maxTokens": {"type": "number", "default": 1000, "required": False, "description": "The maximum number of tokens to generate.", "validation": {"min": 1, "max": 128000}},
                "topP": {"type": "number", "default": 1, "required": False, "description": "The top p of the model.", "validation": {"min": 0, "max": 1}},
                "topK": {"type": "number", "default": 40, "required": False, "description": "The top k of the model.", "validation": {"min": 1, "max": 100}},
                "stopSequences": {"type": "array", "default": [], "required": False, "description": "The stop sequences of the model.", "validation": {"items": {"type": "string"}}},
                "numberOfGenerations": {"type": "number", "default": 1, "required": False, "description": "The number of generations to generate.", "validation": {"min": 1, "max": 10}},
                "supportedResponseFormats": {"type": "array", "default": ["text", "json"], "required": False, "description": "The supported response formats of the model.", "validation": {"items": {"type": "string"}}}
            }
        }
    ]
    
    # Create LLM definitions
    if LLMDefinition:
        for llm_data in llms_data:
            LLMDefinition.objects.using('default').get_or_create(
                model_key=llm_data["modelKey"],
                defaults={
                    "model_provider": llm_data["modelProvider"],
                    "display_name": llm_data["displayName"],
                    "description": llm_data["description"],
                    "supported_modalities": llm_data["supportedModalities"],
                    "max_context_tokens": llm_data["maxContextTokens"],
                    "model_configuration": llm_data["modelConfiguration"],
                    "is_active": True
                }
            )


def seed_test_data(superuser_id: Optional[int] = None, measure_timing: bool = False):
    """
    Seed test data after truncation.
    
    Creates:
    - Superuser (if not already exists)
    - Test accounts (from TEST_ACCOUNTS)
    - Test organizations (from TEST_ORGANIZATIONS)
    - Subscriptions for organizations that need them
    - Test users (from TEST_USERS)
    - Role assignments for users
    - Organization memberships for users
    
    Args:
        superuser_id: ID of superuser to preserve (if exists)
        measure_timing: If True, log timing for each section
    """
    if not DJANGO_AVAILABLE:
        return
    
    def log_seed_timing(operation_name, start_time):
        if measure_timing:
            elapsed = time.time() - start_time
            print(f"[TIMING]   {operation_name}: {elapsed:.3f}s")
        return time.time()
    
    seed_section_start = time.time()
    
    # User = get_user_model()
    superuser_email = os.getenv("ADMIN_EMAIL", "admin@hudhud.ai")
    superuser_password = os.getenv("ADMIN_PASSWORD", "admin123")
    superuser_full_name = os.getenv("ADMIN_FULL_NAME", "Super Admin")

    # Ensure superuser exists
    superuser = None
    if superuser_id:
        try:
            superuser = User.objects.using('default').get(id=superuser_id)
        except User.DoesNotExist:
            superuser = None
    
    if not superuser:
        try:
            superuser = User.objects.using('default').filter(
                Q(email__iexact=superuser_email) | Q(is_superuser=True)
            ).first()
        except Exception:
            pass
    
    if not superuser:
        try:
            # Use .using('default') to ensure we use the real database
            superuser = User.objects.using('default').create_superuser(
                email=superuser_email,
                password=superuser_password,
                full_name=superuser_full_name
            )
        except Exception:
            # If creation fails, try to get any superuser
            superuser = User.objects.using('default').filter(is_superuser=True).first()
    
    if not superuser:
        return  # Cannot proceed without superuser
    
    seed_section_start = log_seed_timing("Superuser lookup in seed", seed_section_start)
    
    if VERBOSE:
        print("SEED 1")
    
    # Create accounts
    accounts_start = time.time()
    create_static_data(superuser)
    associate_account_to_user = hasattr(superuser, 'account')
    print(f"associate_account_to_user: {associate_account_to_user}")
    account_map = {}
    if Account:
        for account_data in TEST_ACCOUNTS:
            account, created = Account.objects.using('default').get_or_create(
                name=account_data["name"],
                defaults={
                    "contact_email": account_data["contact_email"],
                    "description": account_data["description"],
                    "created_by": superuser,
                    "updated_by": superuser,
                    "is_active": True,
                }
            )
            if not created:
                # Update existing account
                account.contact_email = account_data["contact_email"]
                account.description = account_data["description"]
                account.updated_by = superuser
                account.is_active = True
                account.save()
            account_map[account_data["name"]] = account
    
    accounts_start = log_seed_timing("Accounts creation", accounts_start)
    
    if VERBOSE:
        print("SEED 2: ACCOUNTS CREATED")
    
    # Create organizations
    orgs_start = time.time()
    organization_map = {}
    if Organization and Account:
        for org_data in TEST_ORGANIZATIONS:
            account = account_map.get(org_data["account_name"])
            if not account:
                continue
            
            org, created = Organization.objects.using('default').get_or_create(
                account=account,
                name=org_data["name"],
                defaults={
                    "description": f"Test organization: {org_data['name']}",
                    "created_by": superuser,
                    "updated_by": superuser,
                    "is_active": True,
                }
            )
            if not created:
                org.description = f"Test organization: {org_data['name']}"
                org.updated_by = superuser
                org.is_active = True
                org.save()
            organization_map[org_data["name"]] = org
    
    orgs_start = log_seed_timing("Organizations creation", orgs_start)
    
    if VERBOSE:
        print("SEED 3: ORGANIZATIONS CREATED")
    
    # Create subscriptions for organizations that need them
    # Default limits are set high so normal tests (create team, add members) do not hit subscription limits.
    # Edge-case tests that assert limit enforcement override these in the test and restore in finally.
    subs_start = time.time()
    if Subscription and Module and organization_map:
        DEFAULT_MAX_TEAMS = 500
        DEFAULT_MAX_TEAM_MEMBERS = 500
        DEFAULT_MAX_USERS_PER_ORG = 500
        DEFAULT_MAX_ORGS_PER_USER = 500
        for module in Module.objects.using('default').filter(key__in=["USER_MANAGEMENT", "TEAMS_MANAGEMENT", "ROLE_AND_PERMISSION_MANAGEMENT", "FILES_MANAGEMENT"]):
            now = timezone.now()
            for org_data in TEST_ORGANIZATIONS:
                if org_data["has_subscription"]:
                    org = organization_map.get(org_data["name"])
                    if org:
                        configuration = {"session_duration_hours": 24, "max_concurrent_sessions": 5}
                        if org_data.get("max_concurrent_sessions"):
                            configuration["max_concurrent_sessions"] = org_data["max_concurrent_sessions"]
                        if module.key == "TEAMS_MANAGEMENT":
                            configuration["max_teams"] = DEFAULT_MAX_TEAMS
                            configuration["max_team_members"] = DEFAULT_MAX_TEAM_MEMBERS
                        if module.key == "USER_MANAGEMENT":
                            configuration["max_users_per_org"] = DEFAULT_MAX_USERS_PER_ORG
                            configuration["max_orgs_per_user"] = DEFAULT_MAX_ORGS_PER_USER
                        sub, created = Subscription.objects.using('default').get_or_create(
                            organization=org,
                            module=module,
                            defaults={
                                "status": Subscription.Status.ACTIVE,
                                "configuration": configuration,
                                "start_date": now - timedelta(days=30),
                                "end_date": None,
                                "trial_end_date": now - timedelta(days=15),
                            }
                        )
                        if not created:
                            # Ensure existing subscriptions have high limits so tests do not fail on re-runs
                            cfg = sub.configuration or {}
                            updated = False
                            if module.key == "TEAMS_MANAGEMENT":
                                if cfg.get("max_teams") is None or int(cfg.get("max_teams", 0)) < DEFAULT_MAX_TEAMS:
                                    cfg["max_teams"] = DEFAULT_MAX_TEAMS
                                    updated = True
                                if cfg.get("max_team_members") is None or int(cfg.get("max_team_members", 0)) < DEFAULT_MAX_TEAM_MEMBERS:
                                    cfg["max_team_members"] = DEFAULT_MAX_TEAM_MEMBERS
                                    updated = True
                            if module.key == "USER_MANAGEMENT":
                                if cfg.get("max_users_per_org") is None or int(cfg.get("max_users_per_org", 0)) < DEFAULT_MAX_USERS_PER_ORG:
                                    cfg["max_users_per_org"] = DEFAULT_MAX_USERS_PER_ORG
                                    updated = True
                                if cfg.get("max_orgs_per_user") is None or int(cfg.get("max_orgs_per_user", 0)) < DEFAULT_MAX_ORGS_PER_USER:
                                    cfg["max_orgs_per_user"] = DEFAULT_MAX_ORGS_PER_USER
                                    updated = True
                            if updated:
                                sub.configuration = cfg
                                sub.save()
    
    subs_start = log_seed_timing("Subscriptions creation", subs_start)
    
    if VERBOSE:
        print("SEED 4: SUBSCRIPTIONS CREATED")
    
    # Get or create system roles
    roles_start = time.time()
    role_map = {}
    if Role:
        # Account-level roles (organization=None)
        for role_name in [ROLE_ACCOUNT_OWNER, ROLE_ACCOUNT_ADMINISTRATOR, ROLE_SAAS_ACCOUNT_MANAGER, ROLE_SAAS_ADMINISTRATOR]:
            if role_name:
                role, _ = Role.objects.using('default').get_or_create(
                    organization=None,
                    name=role_name,
                    defaults={
                        "role_type": Role.RoleType.SYSTEM,
                        "is_active": True,
                        "created_by": superuser,
                        "permissions": ROLES_PERMISSIONS.get(role_name, []),
                    }
                )
                role_map[("account", role_name)] = role
        


        # Predefined org-scoped roles: Organization Owner, Organization Administrator, Predefined role:Agent Manager, User/Team predefined roles (attached to each organization)
        org_scoped_role_names = [ROLE_AGENT_MANAGER, ROLE_ORGANIZATION_OWNER, ROLE_ORGANIZATION_ADMINISTRATOR] + PREDEFINED_USER_ROLE_NAMES + PREDEFINED_TEAM_ROLE_NAMES
        if organization_map:
            for org_name, org in organization_map.items():
                for role_name in org_scoped_role_names:
                    if not role_name:
                        continue
                    perms = ROLES_PERMISSIONS.get(role_name, [])
                    role_type = (
                        Role.RoleType.SYSTEM
                        if role_name in [ROLE_ORGANIZATION_OWNER, ROLE_ORGANIZATION_ADMINISTRATOR]
                        else Role.RoleType.PREDEFINED_CUSTOM
                    )
                    role, _ = Role.objects.using('default').get_or_create(
                        organization=org,
                        name=role_name,
                        defaults={
                            "role_type": role_type,
                            "is_active": True,
                            "created_by": superuser,
                            "permissions": perms,
                        }
                    )
                    role_map[(org_name, role_name)] = role

    roles_start = log_seed_timing("Roles creation", roles_start)
    
    if VERBOSE:
        print("SEED 5: ROLES CREATED")
    
    # Create users and assign roles/memberships
    users_start = time.time()
    user_map = {}
    if User:
        for user_data in TEST_USERS:
            # Skip users without account_name (like SAAS Account Manager) for now
            account_name = user_data.get("account_name")
            account = account_map.get(account_name) if account_name else None
            
            # Create or get user
            defaults = {
                "full_name": user_data["full_name"],
                "is_active": True,
            }
            if "is_staff" in user_data:
                defaults["is_staff"] = True
            if "is_active" in user_data:
                defaults["is_active"] = user_data["is_active"]
            if associate_account_to_user:
                defaults["account"] = account
            
            user, created = User.objects.using('default').get_or_create(
                email=user_data["email"],
                defaults=defaults,
                # account=account
            )
            if not created:
                user.full_name = user_data["full_name"]
                if associate_account_to_user:
                    user.account = account
                user.is_active = True
                if user_data.get("is_staff"):
                    user.is_staff = True
                if user_data.get("is_active"):
                    user.is_active = user_data["is_active"]
                user.save()
            
            # Set password
            user.set_password(user_data["password"])
            user.save()
            user_map[user_data["email"]] = user
            
            # Set up get_assigned_account_ids for SAAS Account Manager
            assigned_account_names = user_data.get("assigned_account_names")
            if assigned_account_names and hasattr(account_map[assigned_account_names[0]], 'assigned_users'):
                for name in assigned_account_names:
                    if name in account_map:
                        account = account_map[name]
                        account.assigned_users.add(user)
                        account.save()
            
            # Skip account-specific logic if no account
            if not account:
                # Still assign roles if any
                if RoleAssignment and user_data.get("roles", {}).get("account"):
                    for role_name in user_data["roles"]["account"]:
                        role = role_map.get(("account", role_name))
                        if role:
                            RoleAssignment.objects.using('default').get_or_create(
                                user=user,
                                organization=None,
                                role=role,
                                defaults={
                                    "assigned_by": superuser,
                                }
                            )
                continue
            
            # If user is account owner, set account.created_by
            if "Account Owner" in user_data.get("roles", {}).get("account", []):
                account.created_by = user
                account.updated_by = user
                account.save()
            
            # Assign account-level roles
            if RoleAssignment and user_data.get("roles", {}).get("account"):
                for role_name in user_data["roles"]["account"]:
                    role = role_map.get(("account", role_name))
                    if role:
                        RoleAssignment.objects.using('default').get_or_create(
                            user=user,
                            organization=None,
                            role=role,
                            defaults={
                                "assigned_by": superuser,
                            }
                        )
            
            # Assign organization-level roles and memberships
            if UserOrganization:
                org_roles = user_data.get("roles", {}).get("organizations", {})
                memberships = user_data.get("memberships", [])
                
                # Combine orgs from roles and memberships
                all_orgs = set(org_roles.keys()) | set(memberships)
                
                for org_name in all_orgs:
                    org = organization_map.get(org_name)
                    if not org:
                        continue
                    
                    # Create membership
                    membership, _ = UserOrganization.objects.using('default').get_or_create(
                        user=user,
                        organization=org,
                        defaults={
                            "assigned_by": superuser,
                            "is_active": True,
                        }
                    )
                    if not membership.is_active:
                        membership.is_active = True
                        membership.assigned_by = superuser
                        membership.save()
                    
                    # Assign organization-level roles (system org roles by ("org", name), org-scoped by (org_name, name))
                    if RoleAssignment and org_name in org_roles:
                        for role_name in org_roles[org_name]:
                            role = role_map.get(("org", role_name)) or role_map.get((org_name, role_name))
                            if role:
                                RoleAssignment.objects.using('default').get_or_create(
                                    user=user,
                                    organization=org,
                                    role=role,
                                    defaults={
                                        "assigned_by": superuser,
                                    }
                                )
    
    users_start = log_seed_timing("Users and role assignments creation", users_start)
    
    if VERBOSE:
        print("SEED 6: USERS CREATED")


@pytest.fixture(autouse=True)
def truncate_test_data(request, transactional_db):
    """
    Automatically truncate test data tables before each test.
    
    Preserves the superuser (identified by ADMIN_EMAIL or is_superuser=True).
    Truncates tables in the correct order to respect foreign key constraints.
    After truncation, seeds test data (superuser, accounts, organizations, managers, users).
    
    This fixture runs automatically before each test (autouse=True).
    Can be disabled with pytest.mark.no_truncate marker.
    
    Set USE_RAW_TRUNCATE=true for faster truncation using raw SQL (PostgreSQL only).
    Set TRUNCATE_VERBOSE=true to see detailed logging of truncation operations.
    Set MEASURE_FIXTURE_TIMING=true to see timing breakdown for each fixture operation.
    
    Note: Uses a separate database connection to ensure truncation persists
    even if test transactions roll back.
    """
    if not DJANGO_AVAILABLE or "no_truncate" in request.keywords:
        yield
        return
    
    # Configuration
    use_raw_truncate = os.getenv("USE_RAW_TRUNCATE", "false").lower() == "true"
    verbose = os.getenv("TRUNCATE_VERBOSE", str(VERBOSE)).lower() == "true"
    measure_timing = os.getenv("MEASURE_FIXTURE_TIMING", "true").lower() == "true"
    
    fixture_start_time = time.time()
    timing_log = []
    
    def log_timing(operation_name, start_time):
        elapsed = time.time() - start_time
        timing_log.append((operation_name, elapsed))
        if measure_timing:
            print(f"[TIMING] {operation_name}: {elapsed:.3f}s")
        return time.time()
    
    # Get superuser email to preserve
    superuser_email = os.getenv("ADMIN_EMAIL", "admin@hudhud.ai")
    
    # Get superuser ID to preserve (or create if it doesn't exist)
    # This must happen BEFORE truncation and must be committed
    superuser_start = time.time()
    User = get_user_model()
    superuser_id = None
    
    # Ensure superuser exists before truncation
    try:
        # Try to find existing superuser (including soft-deleted)
        if hasattr(User, '_all_objects'):
            superuser = User._all_objects.filter(
                Q(email__iexact=superuser_email) | Q(is_superuser=True)
            ).first()
        else:
            superuser = User.objects.filter(
                Q(email__iexact=superuser_email) | Q(is_superuser=True)
            ).first()
        
        if superuser:
            superuser_id = superuser.id
            if hasattr(superuser, 'deleted_at') and superuser.deleted_at:
                superuser.restore()
                superuser.is_active = True
                superuser.is_superuser = True
                superuser.save()
        else:
            # Create superuser if it doesn't exist
            try:
                superuser = User.objects.create_superuser(
                    email=superuser_email,
                    password=os.getenv("ADMIN_PASSWORD", "admin123")
                )
                superuser_id = superuser.id
                connection.commit()
            except Exception:
                # Try to find any superuser as fallback
                any_superuser = (User._all_objects if hasattr(User, '_all_objects') else User.objects).filter(
                    is_superuser=True
                ).first()
                superuser_id = any_superuser.id if any_superuser else None
    except Exception:
        superuser_id = None
    
    superuser_start = log_timing("Superuser lookup/creation", superuser_start)
    
    # Helper function to delete all records including soft-deleted
    # Uses raw SQL with explicit commit to avoid transaction rollback issues
    def delete_all_including_soft_deleted(model_class, model_name=""):
        """Delete all records including soft-deleted ones using raw SQL."""
        if not model_class:
            return 0
        
        model_name_display = model_name or model_class.__name__
        table_name = model_class._meta.db_table
        
        try:
            # CRITICAL: Use a completely separate connection that's not managed by pytest-django
            # This ensures our DELETE commits independently and persists
            from django.conf import settings
            from django.db import connections
            
            # Get database settings - use the actual database name, not the test database
            # For acceptance tests, we want to use the same database as the API server
            db_settings = settings.DATABASES['default']
            
            # Use the actual database name (e.g., 'appdb'), not the test database
            # pytest-django may have modified the database name to 'test_appdb'
            actual_db_name = os.getenv('DB_NAME', db_settings.get('NAME'))
            if actual_db_name.startswith('test_'):
                # Remove 'test_' prefix if DB_NAME env var not set
                actual_db_name = os.getenv('DB_NAME') or actual_db_name[5:]
            
            # Try to use psycopg (version 3) directly (bypasses Django connection pool)
            try:
                import psycopg
                
                # Connect directly to PostgreSQL, bypassing Django's connection management
                # psycopg3 uses autocommit parameter instead of set_isolation_level
                # Use the actual database name, not the test database
                direct_conn = psycopg.connect(
                    host=db_settings.get('HOST', 'localhost'),
                    port=db_settings.get('PORT', 5432),
                    dbname=actual_db_name,  # Use actual database name, not test database
                    user=db_settings.get('USER'),
                    password=db_settings.get('PASSWORD'),
                    autocommit=True  # psycopg3: autocommit mode so every statement commits immediately
                )
                use_direct_connection = True
            except ImportError:
                if verbose:
                    print(f"[TRUNCATE] psycopg not available, using Django connection")
                # Fallback to Django connection
                direct_conn = None
                use_direct_connection = False
                db_conn = connections['default']
                db_conn.close()
                db_conn.ensure_connection()
            
            if use_direct_connection:
                # Use direct psycopg connection (autocommit mode)
                try:
                    with direct_conn.cursor() as cursor:
                        # Get count and delete all records
                        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                        actual_count = cursor.fetchone()[0]
                        
                        if actual_count > 0:
                            cursor.execute(f'DELETE FROM "{table_name}"')
                            deleted_count = cursor.rowcount
                            if verbose:
                                print(f"[TRUNCATE] Deleted {deleted_count} records from {model_name_display}")
                            
                            # Verify deletion
                            cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                            remaining = cursor.fetchone()[0]
                            if remaining > 0:
                                # Try TRUNCATE as fallback
                                cursor.execute(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE')
                                if verbose:
                                    print(f"[TRUNCATE] Used TRUNCATE CASCADE for {model_name_display}")
                            
                            return deleted_count
                        return 0
                finally:
                    direct_conn.close()
            else:
                # Fallback: Use Django connection with explicit commit
                db_conn = connections['default']
                db_conn.close()
                db_conn.ensure_connection()
                
                with db_conn.cursor() as cursor:
                    cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                    actual_count = cursor.fetchone()[0]
                    
                    if actual_count > 0:
                        cursor.execute(f'DELETE FROM "{table_name}"')
                        db_conn.commit()
                        if verbose:
                            print(f"[TRUNCATE] Deleted {cursor.rowcount} records from {model_name_display}")
                        return cursor.rowcount
                    return 0
        except Exception as e:
            import traceback
            if verbose:
                print(f"[TRUNCATE] Error deleting {model_name_display}: {e}")
                print(f"[TRUNCATE] Traceback: {traceback.format_exc()}")
            # Re-raise the exception so truncation failures are caught and handled
            raise RuntimeError(f"Failed to truncate table {model_name_display} ({table_name}): {e}") from e
    
    truncate_start = time.time()
    truncation_error = None
    
    try:
        if use_raw_truncate:
            # Use raw SQL TRUNCATE for better performance (PostgreSQL)
            try:
                from django.db import connections
                db_conn = connections['default']
                
                with db_conn.cursor() as cursor:
                    cursor.execute("SET session_replication_role = 'replica';")
                    
                    # Collect tables to truncate from get_truncate_tables() list
                    tables = []
                    for model in get_truncate_tables():
                        if model != User:  # User is handled separately
                            tables.append(model._meta.db_table)
                    
                    if tables:
                        table_list = ", ".join([f'"{t}"' for t in tables])
                        cursor.execute(f'TRUNCATE TABLE {table_list} RESTART IDENTITY CASCADE')
                    
                    # Delete users except superuser
                    if User and superuser_id:
                        cursor.execute(f'DELETE FROM "{User._meta.db_table}" WHERE id != %s', [superuser_id])
                    elif User:
                        cursor.execute(f'TRUNCATE TABLE "{User._meta.db_table}" RESTART IDENTITY CASCADE')
                    
                    cursor.execute("SET session_replication_role = 'origin';")
                
                try:
                    db_conn.commit()
                except Exception:
                    pass  # TRUNCATE auto-commits in PostgreSQL
            except Exception as e:
                # Fallback to Django ORM if raw SQL fails
                truncation_error = e
                if verbose:
                    print(f"[TRUNCATE] Raw SQL truncation failed, falling back to ORM: {e}")
                use_raw_truncate = False
        
        if not use_raw_truncate:
            # Use Django ORM delete (slower but more reliable and respects model logic)
            # Truncate tables in order (respecting foreign key constraints)
            # Process all tables from get_truncate_tables() except User
            for model in get_truncate_tables():
                if model != User:  # User is handled separately
                    model_name = model.__name__
                    try:
                        deleted_count = delete_all_including_soft_deleted(model, model_name)
                    except Exception as e:
                        # Re-raise with context
                        raise RuntimeError(f"Failed to truncate table {model_name}: {e}") from e
            
            # User (preserve superuser)
            if User and superuser_id:
                try:
                    from django.db import connections
                    db_conn = connections['default']
                    db_conn.close()
                    db_conn.ensure_connection()
                    with db_conn.cursor() as cursor:
                        cursor.execute(f'DELETE FROM "{User._meta.db_table}" WHERE id != %s', [superuser_id])
                    db_conn.commit()
                except Exception as e:
                    raise RuntimeError(f"Failed to truncate User table (preserving superuser {superuser_id}): {e}") from e
            elif User:
                try:
                    delete_all_including_soft_deleted(User, "User")
                except Exception as e:
                    raise RuntimeError(f"Failed to truncate User table: {e}") from e
    except Exception as e:
        import traceback
        error_msg = (
            f"CRITICAL: Failed to truncate test data tables.\n"
            f"Error: {str(e)}\n"
            f"Traceback:\n{traceback.format_exc()}\n"
            f"This test will be skipped. Please fix the truncation issue before running tests.\n"
            f"Common causes:\n"
            f"  - Database connection issues\n"
            f"  - Foreign key constraint violations\n"
            f"  - Table locking issues\n"
            f"  - Insufficient database permissions"
        )
        if verbose:
            print(f"[TRUNCATE] {error_msg}")
        pytest.skip(error_msg)
    
    truncate_start = log_timing("Truncation", truncate_start)
    
    # Clear Redis rate limit keys to reset rate limits
    # Uses the same method as the app (cache.delete()) via clear_all_login_failures()
    redis_start = time.time()
    try:
        deleted_count = clear_all_login_failures()
        if verbose:
            if deleted_count > 0:
                print(f"[TRUNCATE] Cleared {deleted_count} Redis rate limit keys")
            elif deleted_count == -1:
                print("[TRUNCATE] Cleared all Redis cache (pattern deletion not available)")
            else:
                print("[TRUNCATE] No rate limit keys found to clear")
    except Exception as e:
        # Gracefully handle if Redis is not available or cache clearing fails
        if verbose:
            print(f"[TRUNCATE] Warning: Could not clear Redis rate limits: {e}")
        # Continue with tests even if Redis clearing fails
    
    redis_start = log_timing("Redis clearing", redis_start)
    
    # Seed test data after truncation
    seed_start = time.time()
    try:
        seed_test_data(superuser_id, measure_timing=measure_timing)
    except Exception as e:
        import traceback
        error_msg = (
            f"CRITICAL: Failed to seed test data after truncation.\n"
            f"Error: {str(e)}\n"
            f"Traceback:\n{traceback.format_exc()}\n"
            f"This test will be skipped. Please fix the seeding issue before running tests.\n"
            f"Common causes:\n"
            f"  - Database connection issues\n"
            f"  - Missing required models or dependencies\n"
            f"  - Foreign key constraint violations\n"
            f"  - Invalid test data configuration"
        )
        if verbose:
            print(f"[TRUNCATE] {error_msg}")
        pytest.skip(error_msg)
    
    seed_start = log_timing("Seed test data", seed_start)
    
    # Log total fixture time
    total_time = time.time() - fixture_start_time
    if measure_timing:
        print(f"[TIMING] {'='*50}")
        print(f"[TIMING] Total fixture time: {total_time:.3f}s")
        print(f"[TIMING] {'='*50}")
    
    yield  # Test runs here
    
    # Optional: Cleanup after test (currently we truncate before, so this is redundant)
    # But kept for future use if needed


def clear_all_login_failures():
    """
    Clear all login rate limit keys from cache.
    
    This function is useful for test cleanup to reset rate limits.
    Uses the same cache.delete() method as clear_login_failures().
    
    Returns:
        int: Number of keys deleted, or -1 if full cache clear was used
    """
    if not DJANGO_AVAILABLE:
        return 0
    
    try:
        from django.core.cache import cache
    except ImportError:
        return 0
    
    deleted_count = 0
    
    # Try to get the Redis client to scan for keys
    redis_client = None
    key_prefix = ""
    try:
        # Django Redis cache backend structure
        if hasattr(cache, '_cache'):
            backend = cache._cache
            # Try different ways to access the Redis client
            if hasattr(backend, 'client'):
                redis_client = backend.client
            elif hasattr(backend, '_client'):
                redis_client = backend._client
            elif hasattr(backend, 'get_client'):
                redis_client = backend.get_client()
            
            # Get the key prefix that Django cache uses
            if hasattr(backend, 'key_prefix'):
                key_prefix = backend.key_prefix

            elif hasattr(backend, '_key_prefix'):
                key_prefix = backend._key_prefix
            elif hasattr(backend, 'make_key'):
                # Test to see what prefix is used
                test_key = backend.make_key("test")
                if test_key != "test":
                    key_prefix = test_key.replace("test", "")
    except (AttributeError, Exception):
        pass
    
    if redis_client:
        try:
            # Use Redis SCAN to find all rate limit keys matching auth:login:*
            # Need to match both with and without prefix
            patterns = [f"{key_prefix}auth:login:*", "auth:login:*"] if key_prefix else ["auth:login:*"]
            cursor = 0
            all_keys = set()
            
            # Scan for keys matching the pattern
            for pattern in patterns:
                cursor = 0
                while True:
                    try:
                        # Try SCAN method (Redis 2.8+)
                        cursor, keys = redis_client.scan(cursor, match=pattern, count=100)
                        if keys:
                            for key in keys:
                                if isinstance(key, bytes):
                                    key = key.decode('utf-8')
                                all_keys.add(key)
                        if cursor == 0:
                            break
                    except (AttributeError, TypeError):
                        # If SCAN not available, try delete_pattern method
                        try:
                            if hasattr(redis_client, 'delete_pattern'):
                                keys = redis_client.delete_pattern(pattern)
                                if isinstance(keys, (list, tuple)):
                                    all_keys.update(keys)
                                elif isinstance(keys, int):
                                    deleted_count = keys
                                    break
                        except Exception:
                            pass
                        break
            
            # Delete each key using cache.delete() (same method as the app uses)
            for key in all_keys:
                # Remove cache key prefix to get the original key name
                cache_key = key
                if key_prefix and key.startswith(key_prefix):
                    cache_key = key[len(key_prefix):]
                
                # Use cache.delete() - same method as clear_login_failures()
                cache.delete(cache_key)
                deleted_count += 1
                
        except Exception:
            # If pattern scanning fails, fall back to clearing all cache
            # This is more aggressive but ensures rate limits are reset
            cache.clear()
            deleted_count = -1  # Indicates full cache clear
    else:
        # If we can't access Redis directly, clear all cache
        # This is more aggressive but ensures rate limits are reset
        cache.clear()
        deleted_count = -1  # Indicates full cache clear
    
    return deleted_count


def execute_raw_query(query: str, params: Optional[list] = None) -> int:
    """
    Execute a raw SQL query and return the number of affected rows.
    
    This function is useful for direct database operations like deleting sessions
    or other operations that bypass Django ORM.
    
    Args:
        query: Raw SQL query string (e.g., "DELETE FROM authsession WHERE token_jti = %s")
        params: Optional list of parameters for the query
    
    Returns:
        Number of affected rows
    
    Example:
        execute_raw_query("DELETE FROM authsession WHERE token_jti = %s", ["abc123"])
    """
    if not DJANGO_AVAILABLE:
        raise RuntimeError("Django is not available. Cannot execute raw query.")
    
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            connection.commit()
            return cursor.rowcount
    except Exception as e:
        connection.rollback()
        raise RuntimeError(f"Failed to execute raw query: {e}")


# Helper function for making API requests
def make_request(
    client: requests.Session,
    method: str,
    endpoint: str,
    **kwargs
) -> requests.Response:
    """
    Helper to make API requests with proper URL construction.
    
    Args:
        client: requests.Session with base_url attribute
        method: HTTP method (get, post, put, patch, delete)
        endpoint: API endpoint (e.g., "/accounts/" or "accounts/")
        **kwargs: Additional arguments to pass to requests method
    
    Returns:
        requests.Response object
    """
    # Ensure endpoint starts with /
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint
    
    url = client.base_url + endpoint
    method_func = getattr(client, method.lower())
    return method_func(url, **kwargs)
