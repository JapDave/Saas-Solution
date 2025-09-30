# ROLE-AND-PERMISSION-MANAGEMENT — Role & Permission Management

> **Module Requirements File**
> **Core Module for managing roles and permissions with a multi-layered authorization system**

---

## Module Meta & Overview

**Owner:** Platform Engineering Team
**Version:** 1.0.0
**Last Updated:** 2025-01-27

**Purpose:** Provide comprehensive role and permission management capabilities across all products in the platform. Enable organizations to create custom roles, assign permissions, and manage user access with subscription-based permission filtering.

**Scope:** Role CRUD operations, permission assignment, subscription-based permissions, authorization logic, and role type management. Covers system roles, custom roles, and role assignments.

**Cross-Product Impact:** All products can leverage role and permission management capabilities. Permission system is foundational and available consistently across the entire platform.

---

## Dependencies

**Core Modules:**
- [AUTHENTICATION-AND-AUTHORIZATION](../CORE-MODULES/AUTHENTICATION-AND-AUTHORIZATION.md) - User authentication for role operations
- [SUBSCRIPTION-MANAGEMENT](../CORE-MODULES/SUBSCRIPTION-MANAGEMENT.md) - Permission filtering based on subscriptions
- [ORGANIZATION-MANAGEMENT](../CORE-MODULES/ORGANIZATION-MANAGEMENT.md) - Organization-level role policies
- [USER-MANAGEMENT](../CORE-MODULES/USER-MANAGEMENT.md) - User assignment and membership validation

**Dependency Notes:** Role and permission management is foundational and must be available before other modules that require authorization.

---

## 1. Data Model

### 1.1 Entity: Role
**Fields:**
- `id`: UUID, required, unique identifier
- `organizationId`: UUID, optional, references `Organization.id`
- `name`: string, required, 1-100 chars, unique within organization
- `description`: text, optional, 0-500 chars, role description
- `permissions`: array[string], required, 0-100 permissions, valid permission keys
- `roleType`: enum, required, [system, user, predefined_custom, user_custom]
- `isActive`: boolean, required, default true, role status
- `createdBy`: UUID, required, references `User.id`
- `createdAt`: timestamp, required, ISO 8601, creation time
- `updatedAt`: timestamp, required, ISO 8601, last modification
- `deletedAt`: timestamp, optional, ISO 8601, deletion time

**Ownership/Visibility:** Roles belong to organizations (except system roles). Users can access roles based on permissions. Deleted roles are soft-deleted and retained for 7 years.

**Relationships:**
- Role → Organization: belongs_to (organization owns role, except system roles)
- Role → User: created_by (user who created role)
- Role → RoleAssignment: one_to_many (role can be assigned to multiple users)

### 1.2 Entity: RoleAssignment
**Fields:**
- `id`: UUID, required, unique identifier
- `userId`: UUID, required, references `User.id`
- `organizationId`: UUID, required, references `Organization.id`
- `roleId`: UUID, required, references `Role.id`
- `assignedBy`: UUID, required, references `User.id`
- `assignedAt`: timestamp, required, ISO 8601, assignment time
- `isActive`: boolean, required, default true, assignment status
- `createdAt`: timestamp, required, ISO 8601, creation time
- `updatedAt`: timestamp, required, ISO 8601, last modification
- `deletedAt`: timestamp, optional, ISO 8601, deletion time

**Ownership/Visibility:** Role assignments belong to organizations. Users can view their own assignments. Admins can view all assignments in their scope. Deleted assignments are soft-deleted and retained for 7 years.

**Relationships:**
- RoleAssignment → User: assigned_to (user who has the role)
- RoleAssignment → Organization: belongs_to (organization context)
- RoleAssignment → Role: assigned_role (the role being assigned)

---

## 2. Input Validation

### 2.1 Field-Level Rules
- `name`: Must be unique within organization, 1-100 characters, no special characters except spaces and hyphens
- `permissions`: Must be valid permission keys from subscribed modules, max 100 permissions per role
- `roleType`: Must be one of [system, user, predefined_custom, user_custom]
- `organizationId`: Must reference existing active organization (except for system roles)

### 2.2 Cross-Field Constraints
- If `roleType` is "system", `organizationId` must be null
- If `roleType` is "user", `organizationId` must be null and permissions must be system-level only
- If `roleType` is "predefined_custom" or "user_custom", `organizationId` must be provided
- All permissions in role must be available to organization through active subscriptions

### 2.3 Business Rules
- Users can only create roles in organizations they belong to
- Role names must be unique within the same organization
- System roles can only be assigned to users with @hudhud.ai email addresses
- Custom roles can only include permissions from modules the organization has subscribed to
- Role assignments are validated against user membership in the organization

---

## 3. Workflows & States

### 3.1 State Machine
```
Draft → Active → Archived
  ↓        ↓
Deleted ← Deleted
```

### 3.2 Allowed Actions by State
| State | Allowed Actions | Who Can Perform | Notes |
|-------|----------------|-----------------|-------|
| Draft | activate, delete | creator, admin | Initial role state |
| Active | update, archive, delete | owner, admin | Normal role state |
| Archived | restore, delete | admin | Archived roles |
| Deleted | restore, purge | admin | Soft deleted state |

### 3.3 Workflow Steps
1. **Role Creation**
   - Trigger: User creates new role
   - Steps: Validate permissions → Check organization membership → Validate role name → Create role record
   - Alternates: Permission validation failed → Name conflict → Organization not found
   - Errors: Invalid permissions → Duplicate name → Insufficient permissions

2. **Role Assignment**
   - Trigger: User assigns role to another user
   - Steps: Validate assigner permissions → Check user membership → Validate role availability → Create assignment
   - Alternates: User not in organization → Role not available → Assignment conflict
   - Errors: Insufficient permissions → User not found → Role not found

---

## 4. Exposed Permissions

| Permission Key | Scope | Description | Enforcement Points | Constraints |
|----------------|-------|-------------|-------------------|-------------|
| `roles:create` | org | Create custom roles | Role creation endpoint | Subscription limits |
| `roles:read` | org/team/user | Read role information | Role access | Role permissions |
| `roles:update` | org | Update custom roles | Role update | Owner or admin permission |
| `roles:delete` | org | Delete custom roles | Role deletion | Owner or admin permission |
| `roles:assign` | org | Assign roles to users | Role assignment | Assignment authority |
| `roles:admin` | org | Full role management | All operations | Admin permission |
| `permissions:list` | org | List available permissions | Permission listing | Subscription filtering |

**Permission Notes:** Role permissions are managed through the Role & Permission Management module. Organization admins have full access, and permissions are filtered by subscription availability.

---

## 5. Configurable Subscription Attributes

| Attribute | Type/Units | Min/Max | Applies To | Enforcement | Telemetry | Overage Policy |
|-----------|------------|---------|-----------|------------|----------|----------------|
| `max_custom_roles_per_org` | count | 5-100 | org | Role creation | roles_created | block |
| `max_permissions_per_role` | count | 10-200 | role | Role creation | permissions_assigned | block |
| `max_role_assignments_per_user` | count | 1-20 | user | Role assignment | assignments_created | block |
| `role_assignment_audit_retention_days` | days | 90-2555 | org | Audit policy | assignments_logged | n/a |

**Subscription Notes:** Role limits are enforced at creation time. Permission availability is filtered by subscription status. Audit retention policies apply to role assignments.

---

## 6. Predefined Custom Roles

| Role Name | Scope | Description | Attached Permissions | Editable by Admin? | Notes |
|-----------|-------|-------------|----------------------|--------------------|-------|
| Team Manager | org | Manage team operations | `teams:read`, `teams:update`, `users:read` | yes | Auto-created on Teams subscription |
| Content Manager | org | Manage content and files | `files:read`, `files:update`, `files:delete` | yes | Auto-created on Files subscription |
| Analytics Viewer | org | View analytics and reports | `analytics:read`, `reports:read` | yes | Auto-created on Analytics subscription |

**Role Notes:** Predefined custom roles are created automatically when organizations subscribe to modules. Admins can modify permissions but cannot remove core module permissions.

---

## 7. Role Types

### 7.1 Immutable Roles

#### 7.1.1 System Roles
- **SaaS Administrator**: Full platform access, can manage all organizations and users
- **SaaS Account Manager**: Can manage assigned accounts and their organizations

**Assignment Rules:**
- Can ONLY be granted to users with email addresses belonging to `@hudhud.ai` domain
- Cannot be modified, deleted, or have permissions changed
- Automatically created during platform initialization

#### 7.1.2 User Roles
- **Account Owner**: Full access to account and all its organizations
- **Account Administrator**: Administrative access to account organizations
- **Organization Owner**: Full access to specific organization
- **Organization Administrator**: Administrative access to specific organization

**Assignment Rules:**
- Can be assigned to any user in the organization
- Cannot be modified, deleted, or have permissions changed
- Automatically created during account/organization setup

### 7.2 Custom Roles

#### 7.2.1 Predefined Custom Roles
- Created automatically when organization subscribes to modules
- Based on "Predefined Custom Roles" section in each module specification
- Can be modified by Organization Administrators (permissions can be added/removed)
- Cannot be deleted while organization has active subscription to the module

#### 7.2.2 User-Defined Custom Roles
- Created manually by Organization Administrators
- Fully customizable permissions (within subscription limits)
- Can be modified, deleted, and renamed by Organization Administrators
- Subject to organization's subscription limits and constraints

---

## 8. Requirements

---

### REQ-ROLE-001: Create Custom Role
**Statement:** Authorized users can create custom roles within organizations with proper validation and subscription enforcement.

**Priority:** High

**Details:**
- **Purpose:** Enable organizations to create custom roles for specific needs with proper permission validation
- **Actors & Access:** Organization Owner, Organization Admin with role creation permissions
- **Trigger:** User initiates custom role creation via API or UI
- **Steps:**
  1. Validate user authentication and organization membership
  2. Check user permissions for role creation
  3. Validate role name uniqueness within organization
  4. Validate all permissions are available through subscriptions
  5. Check organization role limits
  6. Create role record with metadata
  7. Log role creation event
- **Data touched/created:** Role entity, audit logs
- **Rules & variations:** Role type validation, permission filtering, subscription limits
- **Errors & fallbacks:** Permission denied, name conflict, subscription limits exceeded
- **Performance & limits:** Max 100 custom roles per organization, 200 permissions per role
- **Security & audit:** Authentication required, permission validation, audit logging
- **Dependencies:** Authentication, Authorization, Subscription modules
- **Cross-product impact:** Available to all products for role management needs

**Acceptance Scenarios:**
1. **Happy Path:** Given Organization Admin with create permissions, When they create valid custom role, Then role is created successfully
2. **Name Conflict:** Given existing role name, When user creates role with same name, Then creation is rejected with conflict error
3. **Permission Denied:** Given user without create permissions, When they attempt role creation, Then access is denied
4. **Subscription Limit:** Given organization at role limit, When user creates role, Then creation is rejected with limit error

---

### REQ-ROLE-002: Retrieve Role Information
**Statement:** Users can retrieve role information based on their permissions and organizational scope.

**Priority:** High

**Details:**
- **Purpose:** Allow users to view role details they have access to with proper data filtering
- **Actors & Access:** Users with read permissions for roles in their scope
- **Trigger:** User requests role information
- **Steps:**
  1. Validate user authentication
  2. Check role existence and status
  3. Evaluate user permissions for role access
  4. Filter role data based on user permissions
  5. Return filtered role information
- **Data touched/created:** Role access logs
- **Rules & variations:** Permission hierarchy, data filtering, scope limitations
- **Errors & fallbacks:** Role not found, insufficient permissions, access denied
- **Performance & limits:** Role retrieval within 100ms
- **Security & audit:** Permission validation, access logging, data filtering
- **Dependencies:** Authentication, Authorization modules
- **Cross-product impact:** Consistent role access across all products

**Acceptance Scenarios:**
1. **Authorized Access:** Given user with role read permissions, When they request role details, Then role information is returned
2. **Unauthorized Access:** Given user without permissions, When they request role details, Then access is denied
3. **Filtered Data:** Given user with limited permissions, When they request role details, Then filtered data is returned
4. **Role Not Found:** Given non-existent role ID, When user requests details, Then 404 error is returned

---

### REQ-ROLE-003: Update Custom Role
**Statement:** Authorized users can update custom roles within their scope with proper validation.

**Priority:** High

**Details:**
- **Purpose:** Allow modification of custom role information and permissions
- **Actors & Access:** Role owners and users with update permissions
- **Trigger:** User updates custom role
- **Steps:**
  1. Validate user permissions to update role
  2. Check role is custom (not system/user role)
  3. Validate role name uniqueness (if changed)
  4. Validate all permissions are available through subscriptions
  5. Update role record
  6. Log role update event
- **Data touched/created:** Role entity (updated), audit logs
- **Rules & variations:** Custom role validation, permission filtering, name uniqueness
- **Errors & fallbacks:** Cannot update system role, permission denied, subscription limits
- **Performance & limits:** Role update within 200ms
- **Security & audit:** Permission validation, change logging, audit trail
- **Dependencies:** Role creation, access control
- **Cross-product impact:** Role updates affect permissions across all products

**Acceptance Scenarios:**
1. **Update Role:** Given role owner, When they update custom role, Then role is updated successfully
2. **System Role:** Given user tries to update system role, When they submit update, Then update is rejected
3. **Permission Denied:** Given user without update permissions, When they attempt update, Then access is denied
4. **Invalid Permissions:** Given user adds unavailable permissions, When they update role, Then update is rejected

---

### REQ-ROLE-004: Delete Custom Role
**Statement:** Authorized users can delete custom roles with proper validation and cleanup.

**Priority:** Medium

**Details:**
- **Purpose:** Remove custom roles that are no longer needed with proper cleanup
- **Actors & Access:** Role owners and users with delete permissions
- **Trigger:** User deletes custom role
- **Steps:**
  1. Validate user permissions to delete role
  2. Check role is custom (not system/user role)
  3. Check if role is assigned to any users
  4. Perform soft delete (set deletedAt timestamp)
  5. Log role deletion event
- **Data touched/created:** Role entity (deletedAt flag), audit logs
- **Rules & variations:** Custom role validation, assignment checking, soft delete
- **Errors & fallbacks:** Cannot delete system role, role has assignments, permission denied
- **Performance & limits:** Role deletion within 300ms
- **Security & audit:** Permission validation, deletion logging, audit trail
- **Dependencies:** Role access control
- **Cross-product impact:** Role deletion affects user permissions across all products

**Acceptance Scenarios:**
1. **Delete Role:** Given role owner, When they delete unused custom role, Then role is soft deleted
2. **System Role:** Given user tries to delete system role, When they submit deletion, Then deletion is rejected
3. **Assigned Role:** Given role assigned to users, When user tries to delete, Then deletion is rejected with assignment details
4. **Permission Denied:** Given user without delete permissions, When they attempt deletion, Then access is denied

---

### REQ-ROLE-005: Assign Role to User
**Statement:** Authorized users can assign roles to users within their scope with proper validation.

**Priority:** Critical

**Details:**
- **Purpose:** Assign roles to users for access control with proper authority validation
- **Actors & Access:** Users with role assignment permissions in their scope
- **Trigger:** User assigns role to another user
- **Steps:**
  1. Validate assigner permissions for role assignment
  2. Check target user exists and is active
  3. Validate target user is member of organization
  4. Check role exists and is available
  5. Validate assignment authority
  6. Create role assignment record
  7. Log assignment event
- **Data touched/created:** RoleAssignment entity, audit logs
- **Rules & variations:** Assignment authority, user membership, role availability
- **Errors & fallbacks:** User not in organization, role not available, insufficient authority
- **Performance & limits:** Role assignment within 150ms
- **Security & audit:** Authority validation, assignment logging, audit trail
- **Dependencies:** User management, role management, organization management
- **Cross-product impact:** Role assignments affect user access across all products

**Acceptance Scenarios:**
1. **Assign Role:** Given user with assignment permissions, When they assign role to organization member, Then assignment is created
2. **Non-Member:** Given user not in organization, When assigner tries to assign role, Then assignment is rejected
3. **Insufficient Authority:** Given user without assignment permissions, When they attempt assignment, Then access is denied
4. **Duplicate Assignment:** Given user already has role, When assigner tries to assign again, Then assignment is rejected

---

### REQ-ROLE-006: Remove Role from User
**Statement:** Authorized users can remove role assignments from users within their scope.

**Priority:** High

**Details:**
- **Purpose:** Remove role assignments from users with proper authority validation
- **Actors & Access:** Users with role removal permissions in their scope
- **Trigger:** User removes role from another user
- **Steps:**
  1. Validate remover permissions for role removal
  2. Check target user has the role assignment
  3. Validate removal authority
  4. Remove role assignment record (soft delete)
  5. Log removal event
- **Data touched/created:** RoleAssignment entity (deletedAt flag), audit logs
- **Rules & variations:** Removal authority, assignment existence, soft delete
- **Errors & fallbacks:** User doesn't have role, insufficient authority, assignment not found
- **Performance & limits:** Role removal within 150ms
- **Security & audit:** Authority validation, removal logging, audit trail
- **Dependencies:** Role assignment, access control
- **Cross-product impact:** Role removal affects user access across all products

**Acceptance Scenarios:**
1. **Remove Role:** Given user with removal permissions, When they remove role from user, Then assignment is removed
2. **No Assignment:** Given user doesn't have role, When remover tries to remove, Then removal is rejected
3. **Insufficient Authority:** Given user without removal permissions, When they attempt removal, Then access is denied
4. **System Role:** Given user tries to remove system role, When they attempt removal, Then removal is rejected

---

### REQ-ROLE-007: List Roles with Pagination
**Statement:** Authorized users can retrieve paginated list of roles they have access to.

**Priority:** High

**Details:**
- **Purpose:** Allow users to browse and search roles within their scope with pagination
- **Actors & Access:** Users with role read permissions in their scope
- **Trigger:** User requests role list
- **Steps:**
  1. Validate user permissions for role listing
  2. Retrieve filtered role list based on user scope
  3. Apply pagination parameters
  4. Return paginated results with metadata
- **Data touched/created:** Role access logs
- **Rules & variations:** Scope filtering, pagination limits, sorting options
- **Errors & fallbacks:** Invalid pagination parameters, insufficient permissions
- **Performance & limits:** Role list retrieval within 200ms, max 100 roles per page
- **Security & audit:** Permission validation, access logging
- **Dependencies:** Role access control
- **Cross-product impact:** Role listing available across all products

**Acceptance Scenarios:**
1. **List Roles:** Given user with read permissions, When they request role list, Then paginated roles are returned
2. **Filtered Results:** Given user with limited scope, When they request role list, Then filtered results are returned
3. **Invalid Pagination:** Given invalid page parameters, When user requests list, Then error is returned
4. **Empty Results:** Given no accessible roles, When user requests list, Then empty list is returned

---

### REQ-ROLE-008: List Available Permissions
**Statement:** Authorized users can retrieve list of permissions available to their organization.

**Priority:** High

**Details:**
- **Purpose:** Allow users to see what permissions are available for role creation based on subscriptions
- **Actors & Access:** Users with permission listing access in their organization
- **Trigger:** User requests available permissions
- **Steps:**
  1. Validate user permissions for permission listing
  2. Retrieve organization's active subscriptions
  3. Determine available permissions from subscribed modules
  4. Return filtered permission list with descriptions
- **Data touched/created:** Permission access logs
- **Rules & variations:** Subscription filtering, permission categorization, scope limitations
- **Errors & fallbacks:** No active subscriptions, insufficient permissions
- **Performance & limits:** Permission list retrieval within 100ms
- **Security & audit:** Permission validation, access logging
- **Dependencies:** Subscription management, module definitions
- **Cross-product impact:** Permission availability affects role creation across all products

**Acceptance Scenarios:**
1. **List Permissions:** Given user with listing permissions, When they request available permissions, Then filtered permissions are returned
2. **No Subscriptions:** Given organization with no subscriptions, When user requests permissions, Then empty list is returned
3. **Filtered Permissions:** Given organization with limited subscriptions, When user requests permissions, Then only subscribed module permissions are returned
4. **Permission Denied:** Given user without listing permissions, When they request permissions, Then access is denied

---

### REQ-ROLE-009: Permission Resolution
**Statement:** System can resolve user permissions based on roles and subscriptions with proper filtering.

**Priority:** Critical

**Details:**
- **Purpose:** Determine what permissions a user has for authorization decisions with subscription filtering
- **Actors & Access:** System (internal authorization service)
- **Trigger:** User attempts to perform an action requiring permission check
- **Steps:**
  1. Retrieve user's active roles in current organization
  2. Retrieve organization's active subscriptions
  3. Determine available permissions from subscribed modules
  4. Calculate intersection of role permissions and available permissions
  5. Return resolved permissions for authorization
- **Data touched/created:** Permission resolution logs
- **Rules & variations:** Subscription filtering, role activation, permission intersection
- **Errors & fallbacks:** User not in organization, no active roles, no subscriptions
- **Performance & limits:** Permission resolution within 50ms
- **Security & audit:** Resolution logging, permission validation
- **Dependencies:** Role management, subscription management, user management
- **Cross-product impact:** Permission resolution is critical for authorization across all products

**Acceptance Scenarios:**
1. **Resolve Permissions:** Given user with roles and active subscriptions, When system resolves permissions, Then correct permissions are returned
2. **No Subscriptions:** Given user with roles but no subscriptions, When system resolves permissions, Then no permissions are returned
3. **Inactive Roles:** Given user with inactive roles, When system resolves permissions, Then only active role permissions are returned
4. **Cross-Organization:** Given user in different organization, When system resolves permissions, Then organization-specific permissions are returned

---

### REQ-ROLE-010: Create Predefined Roles
**Statement:** System automatically creates predefined roles when organization subscribes to modules.

**Priority:** High

**Details:**
- **Purpose:** Provide organizations with ready-to-use roles for subscribed modules automatically
- **Actors & Access:** System (internal subscription service)
- **Trigger:** Organization subscribes to new module
- **Steps:**
  1. Receive subscription creation event
  2. Retrieve predefined roles for the module
  3. Create role records for the organization
  4. Log predefined role creation events
  5. Return created roles confirmation
- **Data touched/created:** Role entities (predefined), audit logs
- **Rules & variations:** Module-specific roles, organization context, automatic creation
- **Errors & fallbacks:** Module not found, role creation failed, subscription invalid
- **Performance & limits:** Predefined role creation within 500ms
- **Security & audit:** System operation logging, role creation audit
- **Dependencies:** Subscription management, module definitions
- **Cross-product impact:** Predefined roles are available across all products for subscribed modules

**Acceptance Scenarios:**
1. **Create Predefined Roles:** Given organization subscribes to module, When system processes subscription, Then predefined roles are created
2. **Multiple Modules:** Given organization subscribes to multiple modules, When system processes subscriptions, Then all predefined roles are created
3. **Module Not Found:** Given invalid module subscription, When system processes subscription, Then error is logged and subscription continues
4. **Role Creation Failed:** Given role creation failure, When system processes subscription, Then error is logged and subscription continues

---

## 9. Error Handling

### Error Messages
- `ROLE_NOT_FOUND`: Role does not exist or has been deleted
- `INSUFFICIENT_PERMISSIONS`: User lacks required permissions for operation
- `ROLE_NAME_CONFLICT`: Role name already exists in organization
- `INVALID_ROLE_TYPE`: Cannot modify system or user roles
- `ROLE_HAS_ASSIGNMENTS`: Cannot delete role with active assignments
- `PERMISSION_NOT_AVAILABLE`: Permission not available through subscriptions
- `ASSIGNMENT_AUTHORITY_DENIED`: User lacks authority to assign/remove roles
- `USER_NOT_IN_ORGANIZATION`: Target user is not member of organization

### Retry Logic
- Role creation failures: 3 retries with exponential backoff
- Permission resolution: No retry, immediate failure
- Role assignment operations: 2 retries with linear backoff

### Idempotency
- Role creation: Use name-based deduplication within organization
- Role assignment: Check existing assignments before creating
- Permission resolution: Cache results for 5 minutes

---

## 10. Security & Audit

### Authentication
- All role operations require valid authentication token
- API keys supported for programmatic access
- Session-based authentication for web access

### Authorization
- Role-level permissions checked on every operation
- Organization and user permissions inherited
- System role assignment restricted to @hudhud.ai emails

### Input Validation
- Role name validation against reserved names
- Permission validation against subscribed modules
- Role type validation for modification operations
- User membership validation for assignments

### Rate Limiting
- 50 role operations per user per hour
- 100 permission resolution requests per user per hour
- 20 role assignments per user per hour

### Audit Logging
- All role operations logged with user, timestamp, and action
- Role assignment attempts logged with success/failure
- Permission resolution logged for security monitoring
- Role changes logged with before/after values

### Data Protection
- Role data encrypted at rest using AES-256
- Permission lists masked in logs for security
- Sensitive role information redacted in audit trails
- Role assignment history retained for compliance

---

## 11. Acceptance Scenarios

### Role Creation Scenarios
1. **Successful Creation**
   - Given: Organization Admin with create permissions
   - When: User creates custom role with valid permissions
   - Then: Role is created and accessible
   - And: Role appears in organization role list

2. **Name Conflict**
   - Given: Existing role with name "Team Lead"
   - When: User creates role with same name
   - Then: Creation is rejected with conflict error
   - And: User is shown available role names

3. **Permission Denied**
   - Given: User without create permissions
   - When: User attempts role creation
   - Then: Access is denied with permission error
   - And: User is shown required permissions

### Role Assignment Scenarios
1. **Successful Assignment**
   - Given: User with assignment permissions
   - When: User assigns role to organization member
   - Then: Assignment is created successfully
   - And: User gains role permissions

2. **Non-Member Assignment**
   - Given: User not in organization
   - When: Assigner tries to assign role
   - Then: Assignment is rejected with membership error
   - And: Assigner is shown organization members

3. **Insufficient Authority**
   - Given: User without assignment permissions
   - When: User attempts role assignment
   - Then: Access is denied with authority error
   - And: User is shown required permissions

---

## 12. Open Questions / Risks / Decisions

### Open Questions
All open questions have been resolved:
1. Role hierarchy: Not implemented, all roles are flat
2. Role inheritance: Not supported, explicit assignment required
3. Temporary role assignments: Not supported, all assignments are permanent
4. Role templates: Not implemented, manual role creation only

### Risks
1. **Permission Complexity**: Complex permission resolution could impact performance
2. **Role Proliferation**: Organizations might create too many custom roles
3. **Assignment Management**: Role assignments could become difficult to manage at scale

### Decisions
1. **Flat Role Structure**: No role hierarchy to simplify permission resolution
2. **Subscription Filtering**: Permissions filtered by subscription status for security
3. **Soft Delete**: Implemented for role and assignment recovery
4. **System Role Protection**: System roles cannot be modified or deleted
5. **Email Domain Restriction**: System roles only for @hudhud.ai emails
6. **Automatic Predefined Roles**: Created on module subscription for user convenience

---

## Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2025-01-27 | Initial version | Requirements Team |
