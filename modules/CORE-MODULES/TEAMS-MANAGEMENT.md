# TEAMS-MANAGEMENT — Team Management

> **Module Requirements File**
> **Core Module for managing teams within organizations with member management and resource sharing**

---

## Module Meta & Overview

**Owner:** SaaS Platform Team
**Version:** 1.0.0
**Last Updated:** 2025-01-27

**Purpose:** Manage teams within organizations with member management and resource sharing. Enable collaborative work environments with proper access controls and subscription-based limits.

**Scope:** Team CRUD operations, member management, shared resources, and team-based permissions. Covers team creation, member assignment, team settings, and resource sharing.

**Cross-Product Impact:** Team management supports all current and future products (Agents Platform, One Inbox, DocVerse). Team structures and permissions are consistently managed across the entire platform.

---

## Dependencies

**Core Modules:**
- [ORGANIZATION-MANAGEMENT](../CORE-MODULES/ORGANIZATION-MANAGEMENT.md) - Teams belong to organizations
- [USER-MANAGEMENT](../CORE-MODULES/USER-MANAGEMENT.md) - Teams are composed of users
- [ROLE-AND-PERMISSION-MANAGEMENT](../CORE-MODULES/ROLE-AND-PERMISSION-MANAGEMENT.md) - Team permissions are managed through roles
- [SUBSCRIPTION-MANAGEMENT](../CORE-MODULES/SUBSCRIPTION-MANAGEMENT.md) - Team creation and size limits are subscription-gated

**Dependency Notes:** Team management depends on organization and user management. Must be available before other modules that require team-based access control.

---

## 1. Data Model

### 1.1 Entity: Team
**Fields:**
- `id`: UUID, required, unique identifier
- `organizationId`: UUID, required, example: "456e7890-e89b-12d3-a456-426614174001", rules: references Organization.id, foreign key
- `name`: string, required, 1-100 chars, example: "Customer Support", rules: unique within organization
- `description`: text, optional, max 500 chars, example: "Handles customer inquiries", rules: nullable
- `configurations`: JSON, optional, default: {}, example: {"maxMembers": 50, "sharedResources": true}, rules: nullable, future use
- `isActive`: boolean, required, default: true, example: true, rules: cannot be null
- `createdBy`: UUID, required, example: "123e4567-e89b-12d3-a456-426614174000", rules: references User.id
- `createdAt`: timestamp, required, ISO 8601, example: "2025-01-01T00:00:00Z", rules: immutable
- `updatedAt`: timestamp, required, ISO 8601, example: "2025-01-01T00:00:00Z", rules: updated on every change
- `deletedAt`: timestamp, optional, ISO 8601, example: null, rules: set on soft delete

**Ownership/Visibility:** Teams belong to organizations. Organization Owners and Admins have full access, Team Managers have management access, Team Members have read access. Deleted teams are soft-deleted and retained for 7 years.

**Relationships:**
- Team → Organization: belongs_to (team belongs to organization)
- Team → User: created_by (user who created team)
- Team → TeamMember: one-to-many (team has multiple members)

### 1.2 Entity: TeamMember
**Fields:**
- `id`: UUID, required, unique identifier
- `teamId`: UUID, required, example: "789e0123-e89b-12d3-a456-426614174002", rules: references Team.id, foreign key
- `userId`: UUID, required, example: "123e4567-e89b-12d3-a456-426614174000", rules: references User.id, foreign key
- `assignedBy`: UUID, required, example: "456e7890-e89b-12d3-a456-426614174001", rules: references User.id
- `assignedAt`: timestamp, required, ISO 8601, example: "2025-01-01T00:00:00Z", rules: immutable
- `isActive`: boolean, required, default: true, example: true, rules: cannot be null
- `createdAt`: timestamp, required, ISO 8601, example: "2025-01-01T00:00:00Z", rules: immutable
- `updatedAt`: timestamp, required, ISO 8601, example: "2025-01-01T00:00:00Z", rules: updated on every change
- `deletedAt`: timestamp, optional, ISO 8601, example: null, rules: set on soft delete

**Ownership/Visibility:** TeamMember records belong to teams. Access follows team hierarchy. Deleted memberships are soft-deleted and retained for 7 years.

**Relationships:**
- TeamMember → Team: belongs_to (member belongs to team)
- TeamMember → User: belongs_to (user who is member)
- TeamMember → User: assigned_by (user who assigned membership)

---

## 2. Input Validation

### 2.1 Field-Level Rules
- `name`: Must be 1-100 characters, unique within organization, cannot be null or empty
- `description`: Must be max 500 characters if provided
- `configurations`: Must be valid JSON if provided
- `isActive`: Must be boolean value
- `organizationId`: Must be valid UUID referencing existing organization
- `userId`: Must be valid UUID referencing existing user

### 2.2 Cross-Field Constraints
- If `deletedAt` is set, team cannot be active
- If `isActive` is false, team members cannot access team resources
- Team name must be unique within the same organization

### 2.3 Business Rules
- Teams must belong to an existing organization
- Team members must be active users in the organization
- Team size must not exceed subscription limits
- Team creation requires appropriate permissions
- Deleted teams cannot be accessed but are retained for compliance

---

## 3. Workflows & States

### 3.1 State Machine
```
Active → Inactive → Deleted
  ↓         ↓
Restored ← Restored
```

### 3.2 Allowed Actions by State
| State | Allowed Actions | Who Can Perform | Notes |
|-------|----------------|-----------------|-------|
| Active | read, update, deactivate, manage_members | owner, admin, manager | Normal team state |
| Inactive | read, activate, delete | owner, admin | Temporarily disabled |
| Deleted | restore, purge | admin | Soft deleted state |

### 3.3 Workflow Steps
1. **Team Creation**
   - Trigger: Authorized user creates new team
   - Steps: Validate permissions → Check subscription limits → Validate data → Create team → Assign initial members → Log creation
   - Alternates: Subscription limit reached → Invalid organization → Permission denied
   - Errors: Validation failure → Database error → Subscription exceeded

2. **Member Management**
   - Trigger: User added/removed from team
   - Steps: Validate permissions → Check team size limits → Validate user membership → Update membership → Update permissions → Log change
   - Alternates: Team size limit reached → User not in organization → User already member
   - Errors: Permission denied → Subscription limit → Database error

3. **Team Status Change**
   - Trigger: Team activated/deactivated
   - Steps: Validate permissions → Check team dependencies → Update status → Notify members → Log change
   - Alternates: Cannot deactivate with active resources → Status already set
   - Errors: Permission denied → Resource conflicts → Notification failure

---

## 4. Exposed Permissions

| Permission Key | Scope | Description | Enforcement Points | Constraints |
|----------------|-------|-------------|-------------------|-------------|
| `teams:create` | org | Create new teams within organization | Team creation endpoint | Subscription limits |
| `teams:read` | org/team | View team information and member lists | Team access endpoint | Team membership or org permissions |
| `teams:update` | org/team | Modify team information and settings | Team update endpoint | Team management permissions |
| `teams:delete` | org | Soft delete teams | Team deletion endpoint | Admin permissions only |
| `teams:manage_members` | org/team | Add and remove users from teams | Member management endpoint | Team size limits |
| `teams:deactivate` | org/team | Deactivate teams | Team status endpoint | Admin permissions |
| `teams:list` | org | List teams in organization | Team list endpoint | Organization membership |
| `teams:view_all` | platform | View all teams across platform | Team retrieval endpoint | SaaS Administrator only |

**Permission Notes:** Team permissions are managed through the Role & Permission Management module. Organization admins have full access, team permissions apply to team management, and individual permissions apply to specific teams.

---

## 5. Configurable Subscription Attributes

| Attribute | Type/Units | Min/Max | Applies To | Enforcement | Telemetry | Overage Policy |
|-----------|------------|---------|-----------|------------|----------|----------------|
| `max_teams` | count | 1-1000 | org | Team creation | teams_created | block |
| `max_team_members` | count | 1-1000 | team | Team member addition | team_members_added | block |
| `team_retention_days` | days | 30-365 | org | Deletion policy | teams_deleted | n/a |

**Subscription Notes:** Team limits are enforced at creation time. Team size limits are enforced when adding members. Soft limits allow temporary overages with notifications. Team retention policies apply to deleted teams.

---

## 6. Predefined Custom Roles

| Role Name | Scope | Description | Attached Permissions | Editable by Admin? | Notes |
|-----------|-------|-------------|----------------------|--------------------|-------|
| Team Manager | org | Manage organization teams | `teams:create`, `teams:read`, `teams:update`, `teams:manage_members` | yes | Auto-created on subscription |
| Team Viewer | org | View organization teams | `teams:read`, `teams:list` | yes | Auto-created on subscription |
| Team Admin | org | Full team management | `teams:create`, `teams:read`, `teams:update`, `teams:delete`, `teams:deactivate`, `teams:manage_members` | yes | Auto-created on subscription |

**Role Notes:** Custom roles are created automatically when organizations subscribe. Admins can modify permissions but cannot remove core team access permissions.

---

## 7. Requirements

---

### REQ-TEAM-001: Create Team
**Statement:** Authenticated users can create new teams within organizations.

**Priority:** High

**Details:**
- **Purpose:** Create teams for collaborative work with shared resources
- **Actors & Access:** Organization Owner, Organization Admin
- **Trigger:** New team needs to be created for collaborative work
- **Steps:**
  1. User provides team details and initial configuration
  2. System validates user permissions for organization
  3. System validates organization subscription for team creation
  4. System validates team information
  5. System creates team record
  6. System creates audit log entry
  7. System returns team details
- **Data touched/created:** Team entity, audit logs
- **Rules & variations:** Team name must be unique within organization, organization must exist and be active, user must have "teams:create" permission, organization must have active subscription with team creation allowance
- **Errors & fallbacks:** Invalid input data, organization subscription does not allow team creation, team count exceeds subscription limits, user lacks permission, organization not found, team name already exists
- **Performance & limits:** Team creation must complete within 2 seconds
- **Security & audit:** Role-based access control for organization access, input validation on all fields, audit logging of team creation
- **Dependencies:** Organization Management, User Management, Role Management, Authorization, Subscription Management modules

**Acceptance Scenarios:**
1. **Happy Path:** Given Organization Owner creates team in their organization, When they provide valid data, Then team is created successfully
2. **Duplicate Name:** Given Organization Owner tries to create team with duplicate name, When they submit, Then 409 conflict error is returned
3. **Invalid Data:** Given Organization Owner creates team with invalid data, When they submit, Then 400 error with validation details is returned

---

### REQ-TEAM-002: Retrieve Team Information
**Statement:** Authenticated users can retrieve team information based on their role and scope.

**Priority:** High

**Details:**
- **Purpose:** Allow users to view team details they have access to
- **Actors & Access:** Organization Owner, Organization Admin, User (if team member)
- **Trigger:** User requests team information
- **Steps:**
  1. User requests team details
  2. System validates user permissions
  3. System retrieves team information
  4. System includes team member list if user has access
  5. System returns filtered team data
- **Data touched/created:** Team entity, TeamMember entity, access logs
- **Rules & variations:** Organization Owner/Admin can view all teams in their organization, User can view teams they're member of, user must have "teams:read" permission or be team member
- **Errors & fallbacks:** User lacks permission and is not team member, team not found
- **Performance & limits:** Team retrieval must complete within 500ms
- **Security & audit:** Role-based access control, data filtering based on user permissions, team membership validation
- **Dependencies:** Authorization module

**Acceptance Scenarios:**
1. **Authorized Access:** Given Team Manager requests team details, When they manage the team, Then team information is returned
2. **Member Access:** Given Team Member requests team details, When they belong to the team, Then team information is returned
3. **Unauthorized Access:** Given user tries to view team they're not member of, When they request details, Then 403 forbidden error is returned

---

### REQ-TEAM-003: Update Team Information
**Statement:** Authenticated users can update team information within their scope.

**Priority:** High

**Details:**
- **Purpose:** Allow team information to be modified as needed
- **Actors & Access:** Organization Owner, Organization Admin
- **Trigger:** Team information needs to be updated
- **Steps:**
  1. User requests team update
  2. System validates user permissions
  3. System validates update data
  4. System updates team record
  5. System creates audit log entry
  6. System returns updated team data
- **Data touched/created:** Team entity, audit logs
- **Rules & variations:** Organization Owner/Admin can update any team in their organization, user must have "teams:update" permission, team name must remain unique within organization
- **Errors & fallbacks:** Invalid update data, user lacks permission, team not found, updated name conflicts with existing team in organization
- **Performance & limits:** Team update must complete within 1 second
- **Security & audit:** Role-based access control, input validation on all fields, audit logging of all changes
- **Dependencies:** Authorization module

**Acceptance Scenarios:**
1. **Successful Update:** Given Team Manager updates team name, When they provide valid data, Then team is updated successfully
2. **Permission Denied:** Given Team Manager tries to update team they don't manage, When they submit, Then 403 forbidden error is returned
3. **Name Conflict:** Given Team Manager updates team name to existing name, When they submit, Then 409 conflict error is returned

---

### REQ-TEAM-004: Add User to Team
**Statement:** Authenticated users can add users to teams.

**Priority:** High

**Details:**
- **Purpose:** Add users to teams for collaborative work
- **Actors & Access:** Organization Owner, Organization Admin
- **Trigger:** User needs to be added to team
- **Steps:**
  1. User requests user addition to team
  2. System validates user permissions for team
  3. System validates organization subscription for team size limits
  4. System validates target user exists and is active
  5. System validates user is member of the organization
  6. System validates user is not already member of team
  7. System creates TeamMember record
  8. System creates audit log entry
  9. System returns updated team membership
- **Data touched/created:** TeamMember entity, audit logs
- **Rules & variations:** Organization Owner/Admin can add users to any team in their organization, user must have "teams:manage_members" permission, target user must be active and member of organization, user must not already be member of team, team size must not exceed subscription limits
- **Errors & fallbacks:** User is not member of organization, user is already member of team, team size exceeds subscription limits, user lacks permission, team or user not found
- **Performance & limits:** User addition must complete within 1 second
- **Security & audit:** Role-based access control, validation of user membership, audit logging of membership changes
- **Dependencies:** Team Management, User Management, Organization Management, Subscription Management modules

**Acceptance Scenarios:**
1. **Successful Addition:** Given Organization Admin adds user to team, When user is member of organization, Then user is added successfully
2. **Already Member:** Given Organization Admin tries to add user already in team, When they submit, Then 400 error with membership details is returned
3. **Size Limit:** Given Organization Admin tries to add user when team size limit reached, When they submit, Then 400 error with size limit is returned

---

### REQ-TEAM-005: Remove User from Team
**Statement:** Authenticated users can remove users from teams.

**Priority:** High

**Details:**
- **Purpose:** Remove user access to team and shared resources
- **Actors & Access:** Organization Owner, Organization Admin
- **Trigger:** User needs to be removed from team
- **Steps:**
  1. User requests user removal from team
  2. System validates user permissions for team
  3. System validates target user is member of team
  4. System removes TeamMember record
  5. System creates audit log entry
  6. System returns updated team membership
- **Data touched/created:** TeamMember entity, audit logs
- **Rules & variations:** Organization Owner/Admin can remove users from any team in their organization, user must have "teams:manage_members" permission, user must be member of team to remove
- **Errors & fallbacks:** User is not member of team, user lacks permission, team or user not found
- **Performance & limits:** User removal must complete within 1 second
- **Security & audit:** Role-based access control, validation of user membership, audit logging of membership changes
- **Dependencies:** Team Management module

**Acceptance Scenarios:**
1. **Successful Removal:** Given Organization Admin removes user from team, When user is member, Then user is removed successfully
2. **Not Member:** Given Organization Admin tries to remove user not in team, When they submit, Then 400 error with membership details is returned
3. **Account Owner:** Given Organization Owner removes user from team, When they submit, Then user is removed successfully

---

### REQ-TEAM-006: Deactivate Team
**Statement:** Authenticated users can deactivate teams to prevent access while preserving data.

**Priority:** Medium

**Details:**
- **Purpose:** Temporarily disable team access without data loss
- **Actors & Access:** Organization Owner, Organization Admin
- **Trigger:** Team needs to be temporarily disabled
- **Steps:**
  1. User requests team deactivation
  2. System validates user permissions
  3. System deactivates team (sets isActive to false)
  4. System creates audit log entry
  5. System returns updated team status
- **Data touched/created:** Team entity (isActive field), audit logs
- **Rules & variations:** Organization Owner/Admin can deactivate any team in their organization, user must have "teams:update" permission, deactivated teams cannot be accessed by users, team members retain their individual organization roles
- **Errors & fallbacks:** User lacks permission, team not found
- **Performance & limits:** Team deactivation must complete within 1 second
- **Security & audit:** Role-based access control, audit logging of deactivation
- **Dependencies:** Authorization module

**Acceptance Scenarios:**
1. **Successful Deactivation:** Given Organization Admin deactivates team, When they submit, Then team is deactivated successfully
2. **Permission Denied:** Given Organization Admin tries to deactivate team without permission, When they submit, Then 403 forbidden error is returned
3. **Access Denied:** Given team is deactivated, When team members try to access team, Then access is denied

---

### REQ-TEAM-007: Delete Team (Soft Delete)
**Statement:** Authenticated users can soft delete teams for data retention compliance.

**Priority:** Low

**Details:**
- **Purpose:** Remove teams from active use while preserving data for compliance
- **Actors & Access:** Organization Owner, Organization Admin
- **Trigger:** Team needs to be permanently removed
- **Steps:**
  1. User requests team deletion
  2. System validates user permissions
  3. System performs soft delete (sets deletedAt timestamp)
  4. System creates audit log entry
  5. System returns deletion confirmation
- **Data touched/created:** Team entity (deletedAt field), audit logs
- **Rules & variations:** Organization Owner/Admin can delete teams in their organization, soft delete preserves all data for compliance, deleted teams cannot be accessed by any user
- **Errors & fallbacks:** User lacks permission, team not found
- **Performance & limits:** Team deletion must complete within 2 seconds
- **Security & audit:** Role-based access control, comprehensive audit logging
- **Dependencies:** Authorization, Audit modules

**Acceptance Scenarios:**
1. **Successful Deletion:** Given Organization Owner deletes team in their organization, When they submit, Then team is soft deleted successfully
2. **Permission Denied:** Given Organization Owner tries to delete team without permission, When they submit, Then 403 forbidden error is returned
3. **Access Denied:** Given team is soft deleted, When any user tries to access it, Then 404 not found error is returned

---

### REQ-TEAM-008: List Teams with Pagination
**Statement:** Authenticated users can retrieve paginated list of teams they have access to.

**Priority:** High

**Details:**
- **Purpose:** Allow users to browse and search teams within their scope
- **Actors & Access:** Organization Owner, Organization Admin, User
- **Trigger:** User requests team list
- **Steps:**
  1. User requests team list with pagination parameters
  2. System validates user permissions
  3. System retrieves filtered team list
  4. System applies pagination
  5. System returns paginated results
- **Data touched/created:** Team entity list, pagination metadata
- **Rules & variations:** Organization Owner/Admin can view all teams in their organization, User can view teams they're member of, user must have "teams:read" permission or be team member, default page size: 25, maximum: 100
- **Errors & fallbacks:** Invalid pagination parameters, user lacks permission and is not team member
- **Performance & limits:** Team list retrieval must complete within 1 second
- **Security & audit:** Role-based access control, data filtering based on user permissions
- **Dependencies:** Authorization module

**Acceptance Scenarios:**
1. **Successful List:** Given Organization Owner requests team list, When they access endpoint, Then teams in their organization are returned with pagination
2. **Organization Admin:** Given Organization Admin requests team list, When they access endpoint, Then teams in their organization are returned
3. **Invalid Pagination:** Given user requests team list with invalid page size, When they submit, Then 400 error with valid range is returned

---

## 8. Error Handling

### Error Messages
- `TEAM_NOT_FOUND`: Team does not exist or has been deleted
- `INSUFFICIENT_PERMISSIONS`: User lacks required permissions for operation
- `TEAM_NAME_EXISTS`: Team name already exists in organization
- `INVALID_TEAM_DATA`: Team data validation failed
- `ORGANIZATION_NOT_FOUND`: Target organization does not exist
- `USER_ALREADY_MEMBER`: User is already member of team
- `USER_NOT_MEMBER`: User is not member of team
- `TEAM_SIZE_LIMIT_EXCEEDED`: Team size exceeds subscription limits
- `SUBSCRIPTION_LIMIT_EXCEEDED`: Organization team count exceeds subscription limits
- `INVALID_PAGINATION`: Invalid pagination parameters provided

### Retry Logic
- Team creation failures: 3 retries with exponential backoff
- Permission checks: No retry, immediate failure
- Database operations: 2 retries with linear backoff

### Idempotency
- Team creation: Use name-based deduplication within organization
- Team updates: Check existing data before updating
- Membership changes: Check existing membership before creating

---

## 9. Security & Audit

### Authentication
- All team operations require valid authentication token
- API keys supported for programmatic access
- Session-based authentication for web access

### Authorization
- Team-level permissions checked on every access
- Organization permissions inherited
- Role-based access control enforced

### Input Validation
- Team name validation and uniqueness checking
- Team data sanitization to prevent injection attacks
- User membership validation
- Subscription limit validation

### Rate Limiting
- 100 team operations per user per hour
- 1000 team list requests per user per hour
- 10 team creations per organization per hour

### Audit Logging
- All team operations logged with user, timestamp, and action
- Team access attempts logged with success/failure
- Team membership changes logged with grantor and grantee
- Team configuration changes logged

### Data Protection
- Team data encrypted at rest using AES-256
- Sensitive team data masked in logs
- Team member lists protected by access control
- Team content not logged in audit trails

---

## 10. Acceptance Scenarios

### Team Creation Scenarios
1. **Successful Creation**
   - Given: Organization Owner with create permissions
   - When: User creates new team with valid data
   - Then: Team is created successfully
   - And: Team is accessible to creator

2. **Permission Denied**
   - Given: User without create permissions
   - When: User attempts to create new team
   - Then: Creation is rejected with permission error
   - And: Attempt is logged for security

3. **Duplicate Name**
   - Given: Team with existing name in organization
   - When: Creation is attempted
   - Then: Creation is rejected with name conflict error
   - And: User is shown name uniqueness requirement

### Team Access Scenarios
1. **Authorized Access**
   - Given: User with read permissions for team
   - When: User requests team details
   - Then: Team information is returned
   - And: Access is logged

2. **Unauthorized Access**
   - Given: User without team permissions
   - When: User attempts to access team details
   - Then: Access is denied with permission error
   - And: Attempt is logged for security

3. **Member Access**
   - Given: Team member accessing their team
   - When: User requests team details
   - Then: Team information is returned
   - And: Access is logged as member access

### Team Membership Scenarios
1. **Add Member**
   - Given: User with membership management permissions
   - When: User adds member to team
   - Then: Membership is created successfully
   - And: User gains team access

2. **Remove Member**
   - Given: User with membership management permissions
   - When: User removes member from team
   - Then: Membership is removed successfully
   - And: User loses team access

3. **Size Limit**
   - Given: Team at size limit
   - When: User attempts to add member
   - Then: Addition is rejected with size limit error
   - And: User is shown subscription upgrade option

---

## 11. Open Questions / Risks / Decisions

### Open Questions
All open questions have been resolved:
1. Team resource sharing: Handled by Files Management module
2. Team notification preferences: Included in team configurations JSON field
3. Team collaboration features: Handled by product-specific modules
4. Team data export: Not implemented in this module

### Risks
1. **Data Consistency**: Team membership changes could lead to data inconsistency
2. **Performance**: Large team volumes could impact query performance
3. **Security**: Team data breaches could affect multiple users

### Decisions
1. **Soft Delete**: Implemented for data recovery and compliance
2. **Subscription Limits**: Team creation and size limits enforced based on subscription
3. **Permission Management**: Delegated to Role & Permission Management module
4. **Resource Sharing**: Delegated to Files Management module
5. **Multi-Organization**: Teams belong to single organization for simplicity
6. **Member Management**: Users must be organization members before team membership

---

## Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2025-01-27 | Initial version with comprehensive requirements | Requirements Team |
