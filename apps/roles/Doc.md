# Roles & Permissions Module Documentation

This document provides a comprehensive guide to the roles and permissions system used in the Hudhud Backend. It covers the core concepts, setup, and usage patterns for controlling access to API endpoints.

## 1. Core Concepts

The authorization system is built on three main models:

- **`Role`**: A named collection of permission keys. Roles can be global (System Roles like "SaaS Administrator") or specific to an `Organization` (e.g., a custom "Auditor" role).
- **`Permission`**: A string key representing a specific action (e.g., `"user:invite"`, `"billing:view"`).
- **`RoleAssignment`**: The link between a `User`, a `Role`, and an optional `Organization`. This is how a user is granted a role's permissions.

## 2. System Initialization

The platform comes with a set of predefined system and template roles. These are created using a Django management command.

### `initialize_roles` Command

This command seeds the immutable system and template roles defined in `apps/roles/management/commands/initialize_roles.py`.

**When it runs**

- `docker/entrypoint.sh` executes `python manage.py initialize_roles` automatically after migrations so containers always have the canonical roles.
- You can rerun it manually whenever role definitions change:

```bash
docker compose -f docker/compose.yaml run --rm web python manage.py initialize_roles
```

**What it creates**

- System roles (`Role.RoleType.SYSTEM`)
  - `SaaS Administrator`: receives every permission in `apps.roles.constants.ROLE_PERMISSION_TEMPLATES["SaaS Administrator"]`.
  - `SaaS Account Manager`: account- and organization-level visibility scoped to assigned accounts.
- Account templates (`Role.RoleType.USER`)
  - `Account Owner`: full account control including billing, members, and organizations.
  - `Account Administrator`: delegated account administration (CRUD on organizations, team/member management).
- Organization templates (`Role.RoleType.USER`)
  - `Organization Owner`: ownership, advanced member management, and team operations.
  - `Organization Administrator`: daily administration (member + team management) without destructive actions.

All permissions loaded by the command are normalised (lowercase `scope:action`) through the serializer helper so database state stays consistent.

To add or modify defaults, update `apps/roles/constants.ROLE_PERMISSION_TEMPLATES` and rerun the command.

## 3. Low-Level Utility Functions

For use in services, Celery tasks, or other non-view logic, two primary utility functions are available in `apps.roles.utils`.

### `has_role(user, role_name, organization_uuid=None)`

Checks if a user is assigned a specific role.

- **`user`**: The user instance to check.
- **`role_name`**: The name of the role (e.g., `"SaaS Administrator"`).
- **`organization_uuid`**: **Required** for non-system roles. If `None`, it checks for a global role assignment.

**Validation**: The function will raise a `ValueError` if you check for a non-system role (like `"Organization Owner"`) without providing an `organization_uuid`.

**Examples:**
```python
from apps.roles.utils import has_role
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR, ROLE_ORGANIZATION_OWNER

# Check for a global (system) role
if has_role(request.user, ROLE_SAAS_ADMINISTRATOR):
    print("User is a SaaS Admin.")

# Check for an organization-specific role
org_uuid = "..."
if has_role(request.user, ROLE_ORGANIZATION_OWNER, organization_uuid=org_uuid):
    print("User is an Owner of this organization.")

# This will raise a ValueError
# has_role(request.user, ROLE_ORGANIZATION_OWNER)
```

### `has_permission(user, permission_key, organization_uuid)`

Checks if a user has a specific permission key through any of their assigned roles.

- **`user`**: The user instance to check.
- **`permission_key`**: The permission string (e.g., `"users.invite"`).
- **`organization_uuid`**: **Required** for non-system permissions.

**Examples:**
```python
from apps.roles.utils import has_permission

# Check for an organization-specific permission
org_uuid = "..."
if has_permission(request.user, "users.invite", organization_uuid=org_uuid):
    print("User can invite users to this organization.")

# This will raise a ValueError
# has_permission(request.user, "users.invite")
```

## 4. DRF Permission Classes

For protecting API endpoints (views), the standard approach is to use DRF Permission Classes. These classes are found in `apps/roles/permissions.py`.

### Predefined Role-Specific Classes

These classes are hard-coded to check for a single, specific role. They are simple to use but less flexible than the generic classes.

- `IsSaaSAdmin`
- `ISSaaSAccountManager`
- `IsOrganizationOwner`
- `IsOrganizationAdmin`

**Usage:**
```python
# in a viewset
from apps.roles.permissions import IsSaaSAdmin

class SomeAdminViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsSaaSAdmin]
    # ...
```

### Generic, Reusable Classes

These are the **recommended** classes for all new development as they are highly flexible and configurable.

#### `HasRole(role_name)`

Checks if the user has the specified `role_name`. It automatically detects if the role is system-level or if it needs an `organization_uuid` from the URL.

**Usage (in `get_permissions`):**
This is the best way to apply permissions to specific actions within a viewset.

```python
# In apps/products/views.py
from rest_framework.permissions import IsAuthenticated
from apps.roles.permissions import HasRole
from apps.roles.constants import ROLE_SAAS_ADMINISTRATOR

class ModuleViewSet(viewsets.ReadOnlyModelViewSet):
    # ...
    def get_permissions(self):
        """
        - 'config_schema' action requires the 'SaaS Administrator' role.
        - All other actions require standard authentication.
        """
        if self.action == "config_schema":
            return [IsAuthenticated(), HasRole(ROLE_SAAS_ADMINISTRATOR)]
        
        return super().get_permissions()
```

#### `HasPermission(permission_key)`

Checks if the user has the specified `permission_key`. This is the most flexible approach, as it decouples your endpoint from specific roles. You can change which roles have a permission without changing any view code.

**Usage (in `get_permissions`):**

```python
# In apps/products/views.py
from rest_framework.permissions import IsAuthenticated
from apps.roles.permissions import HasPermission

class ModuleViewSet(viewsets.ReadOnlyModelViewSet):
    # ...
    def get_permissions(self):
        """
        - 'config_schema' action requires the 'config_schema:read' permission.
        - All other actions require standard authentication.
        """
        if self.action == "config_schema":
            # The permission key "config_schema:read" must be in SYSTEM_PERMISSIONS
            # or the view's URL must contain an <organization_uuid>.
            return [IsAuthenticated(), HasPermission("config_schema:read")]
        
        return super().get_permissions()
```

---

## 5. Summary of Best Practices

1.  **Use `HasPermission` for new endpoints.** It provides the most flexibility. Only use `HasRole` if an action is truly tied to a role title rather than a capability.
2.  **Use `get_permissions()`** in your viewsets to apply different permissions to different actions (`list`, `create`, `destroy`, custom actions, etc.).
3.  **Define permission keys** in a structured way (e.g., `resource.action` like `users.invite`).
4.  **Add new system permissions** to the `SYSTEM_PERMISSIONS` set in `apps/roles/constants.py` if they are not tied to an organization.
5.  **Use the utility functions** `has_role` and `has_permission` for any authorization logic outside of DRF views.
