ROLE_SAAS_ADMINISTRATOR = "SaaS Administrator"
ROLE_SAAS_ACCOUNT_MANAGER = "SaaS Account Manager"
ROLE_ACCOUNT_OWNER = "Account Owner"
ROLE_ACCOUNT_ADMINISTRATOR = "Account Administrator"
ROLE_ORGANIZATION_OWNER = "Organization Owner"
ROLE_ORGANIZATION_ADMINISTRATOR = "Organization Administrator"

# A set of roles that are considered system-level (not tied to an organization)
SYSTEM_ROLES = {
    ROLE_SAAS_ADMINISTRATOR,
    ROLE_SAAS_ACCOUNT_MANAGER,
}


# Permission keys used across the platform
PERMISSION_ACCOUNTS_LIST = "accounts:list"
PERMISSION_ACCOUNTS_READ = "accounts:read"
PERMISSION_ACCOUNTS_CREATE = "accounts:create"
PERMISSION_ACCOUNTS_UPDATE = "accounts:update"
PERMISSION_ACCOUNTS_DELETE = "accounts:delete"

PERMISSION_ORGANIZATIONS_LIST = "organizations:list"
PERMISSION_ORGANIZATIONS_CREATE = "organizations:create"
PERMISSION_ORGANIZATIONS_READ = "organizations:read"
PERMISSION_ORGANIZATIONS_UPDATE = "organizations:update"
PERMISSION_ORGANIZATIONS_DELETE = "organizations:delete"
PERMISSION_ORGANIZATIONS_ASSIGN_OWNER = "organizations:assign_owner"

PERMISSION_TEAMS_LIST = "teams:list"
PERMISSION_TEAMS_CREATE = "teams:create"
PERMISSION_TEAMS_READ = "teams:read"
PERMISSION_TEAMS_UPDATE = "teams:update"
PERMISSION_TEAMS_DELETE = "teams:delete"
PERMISSION_TEAMS_MANAGE_MEMBERS = "teams:manage_members"

SYSTEM_PERMISSIONS = {
    PERMISSION_ACCOUNTS_LIST,
    PERMISSION_ACCOUNTS_READ,
    PERMISSION_ACCOUNTS_CREATE,
    PERMISSION_ACCOUNTS_UPDATE,
    PERMISSION_ACCOUNTS_DELETE,
}
