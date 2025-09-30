# ORGANIZATION-MANAGEMENT — Organization Management

> **Module Requirements File**
> **Core Module for managing organizations within enterprise accounts with complete data isolation**

---

## Module Meta & Overview

**Module Type:** Core

**Owner:** SaaS Platform Team

**Version:** 1.0.0

**Last Updated:** 2025-09-20

**Purpose:** Manage organizations within enterprise accounts with complete data isolation.

**Scope:** Organization CRUD operations, lifecycle management, and enterprise-level administration.

**Success Criteria:** Support 10,000+ organizations with complete tenant isolation.

**Cross-Product Impact:** Organization management supports all current and future products (Agents Platform, One Inbox, DocVerse).

---

## Dependencies

**Core Modules:**
- [ACCOUNT-MANAGEMENT](../CORE-MODULES/ACCOUNT-MANAGEMENT.md) - Organizations belong to an account.
- [AUTHENTICATION-AND-AUTHORIZATION](../CORE-MODULES/AUTHENTICATION-AND-AUTHORIZATION.md) - For authenticating users making organization management requests.
- [USER-MANAGEMENT](../CORE-MODULES/USER-MANAGEMENT.md) - Organization ownership and membership.
- [ROLE-AND-PERMISSION-MANAGEMENT](../CORE-MODULES/ROLE-AND-PERMISSION-MANAGEMENT.md) - For assigning roles like Organization Owner.

**Dependency Notes:** Organization management is a foundational module that builds upon Account Management.

---

## 1. Data Model

### 1.1 Entity: Organization
**Fields:**
- `organizationId`: integer, auto-generated, unique, required, example: 201, rules: primary key
- `accountId`: integer, required, example: 101, rules: references Account.accountId, foreign key
- `name`: string, 1-100 chars, required, example: "Marketing Department", rules: unique within account
- `description`: text, max 500 chars, optional, example: "Handles all marketing activities", rules: nullable
- `logoUrl`: string, valid URL format, optional, example: "https://example.com/logo.png", rules: nullable, must be accessible
- `isActive`: boolean, default true, required, example: true, rules: cannot be null
- `createdBy`: integer, required, example: 12345, rules: references User.userId
- `createdAt`: timestamp, auto-generated, required, example: "2025-01-01T00:00:00Z", rules: immutable
- `updatedAt`: timestamp, auto-generated, required, example: "2025-01-01T00:00:00Z", rules: updated on every change
- `deletedAt`: timestamp, nullable, example: null, rules: set on soft delete

**Ownership/Visibility:**
- SaaS Administrator: full read/write access to all organizations.
- SaaS Account Manager: read access to organizations in assigned accounts.
- Account Owner: full read/write access to organizations in their account.
- Account Admin: read access to organizations in their account.
- Organization Owner: full read/write access to their organization only.
- Organization Admin: read access to their organization only.
- Retention: soft-deleted organizations retained for 7 years for compliance.
- Masking/redaction: logo URL visible only to authorized users.

**Relationships:**
- Organization → Account: many-to-one (an organization belongs to one account)
- Organization → User: one-to-many (through memberships)
- Organization → Team: one-to-many

---

## 2. Input Validation

### 2.1 Field-Level Rules
- `name`: required, string, 1-100 chars, unique within the account.
- `description`: optional, text, max 500 chars.
- `logoUrl`: optional, valid URL format.

### 2.2 Cross-Field Constraints
- `accountId` must exist and be an active account.

### 2.3 Business Rules
- Organization name must be unique within the same account.

---

## 3. Workflows & States

### 3.1 State Machine
```
Active → Inactive → Deleted
```

### 3.2 Allowed Actions by State
| State | Allowed Actions | Who Can Perform | Notes |
|---|---|---|---|
| Active | update, deactivate, delete, list, get, assign owner | SaaS Admin, Account Owner, Org Owner | Normal state |
| Inactive | activate | SaaS Admin, Account Owner, Org Owner | Organization is disabled |
| Deleted | none | - | Soft-deleted, retained for compliance |

---

## 4. Exposed Permissions
| Permission Key | Scope | Description | Enforcement Points | Constraints |
|---|---|---|---|---|
| `organization:create` | account | Create a new organization | Organization creation endpoint | SaaS Administrator, Account Owner, Account Admin |
| `organization:read` | organization | Read organization information | Organization retrieval endpoint | Organization Owner, Organization Admin, Account Owner, Account Admin, SaaS Account Manager (assigned accounts only) |
| `organization:update` | organization | Update organization information | Organization update endpoint | Organization Owner, Account Owner, Account Admin, SaaS Administrator |
| `organization:delete` | account | Delete an organization | Organization deletion endpoint | SaaS Administrator, Account Owner, Account Admin |
| `organization:list` | account | List organizations in an account | Organization list endpoint | SaaS Administrator, SaaS Account Manager (assigned accounts only), Account Owner, Account Admin |
| `organization:assign_owner`| organization | Assign an owner to an organization | Assign owner endpoint | SaaS Administrator, Account Owner, Account Admin |


---

---

## 5. Requirements

### REQ-ORG-001: Create Organization
**Statement**: Authorized users can create new organizations within enterprise accounts.
**Priority**: Critical
**Details**:
- **Purpose**: Create business units within enterprise accounts with isolated resources.
- **Actors**: SaaS Administrator, Account Owner, Account Admin.
- **Trigger**: New business unit needs to be created within an account.
- **Dependencies**: `ACCOUNT-MANAGEMENT`, `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **Happy Path:** Given Account Owner creates organization in their account, When they provide valid data, Then organization is created successfully.
2. **Unauthorized:** Given Account Owner tries to create organization in a different account, When they submit, Then 403 forbidden error is returned.
3. **Duplicate Name:** Given Account Owner creates organization with a duplicate name within the same account, When they submit, Then 409 conflict error is returned.

### REQ-ORG-002: Retrieve Organization Information
**Statement**: Authorized users can retrieve organization information based on their role and scope.
**Priority**: Critical
- **Actors**: SaaS Administrator, SaaS Account Manager, Account Owner, Account Admin, Organization Owner, Organization Admin.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **Org Owner:** Given Organization Owner requests their organization details, When they access endpoint, Then organization information is returned.
2. **Account Owner:** Given Account Owner requests organization in their account, When they access endpoint, Then organization information is returned.
3. **Unauthorized:** Given Account Owner tries to access organization in a different account, When they request details, Then 403 forbidden error is returned.

### REQ-ORG-003: Update Organization Information
**Statement**: Authorized users can update organization information within their scope.
**Priority**: High
- **Actors**: SaaS Administrator, Account Owner, Account Admin, Organization Owner.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **Happy Path:** Given Organization Owner updates their organization name, When they submit valid data, Then organization is updated successfully.
2. **Unauthorized:** Given Organization Owner tries to update a different organization, When they submit, Then 403 forbidden error is returned.
3. **URL Validation:** Given Organization Owner updates logo URL, When they submit, Then URL validation is performed.

### REQ-ORG-004: Deactivate Organization
**Statement**: Authorized users can deactivate organizations to prevent access while preserving data.
**Priority**: High
- **Actors**: SaaS Administrator, Account Owner, Account Admin, Organization Owner.
- **Dependencies**: `SUBSCRIPTION-MANAGEMENT`

**Acceptance Scenarios**:
1. **Happy Path:** Given Organization Owner deactivates their organization, When organization has no active subscriptions, Then organization is deactivated successfully.
2. **With Subscriptions:** Given Organization Owner tries to deactivate organization with active subscriptions, When they submit, Then 400 error with subscription details is returned.
3. **Account Owner:** Given Account Owner deactivates organization in their account, When they submit, Then organization is deactivated successfully.

### REQ-ORG-005: Delete Organization (Soft Delete)
**Statement**: Authorized users can soft delete organizations for data retention compliance.
**Priority**: Medium
- **Actors**: SaaS Administrator, Account Owner, Account Admin.
- **Dependencies**: `SUBSCRIPTION-MANAGEMENT`

**Acceptance Scenarios**:
1. **Happy Path:** Given Account Owner deletes organization with no active subscriptions, When they submit, Then organization is soft deleted successfully.
2. **With Subscriptions:** Given Account Owner tries to delete organization with active subscriptions, When they submit, Then 400 error with subscription details is returned.
3. **Access after delete:** Given organization is soft deleted, When any user tries to access it, Then 404 not found error is returned.

### REQ-ORG-006: List Organizations with Pagination
**Statement**: Authorized users can retrieve paginated list of organizations they have access to.
**Priority**: High
- **Actors**: SaaS Administrator, SaaS Account Manager, Account Owner, Account Admin.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **Account Owner:** Given Account Owner requests organization list, When they access endpoint, Then organizations in their account are returned with pagination.
2. **SaaS Admin:** Given SaaS Administrator requests organization list, When they access endpoint, Then all organizations are returned.
3. **Invalid Pagination:** Given user requests organization list with invalid page size, When they submit, Then 400 error with valid range is returned.

### REQ-ORG-007: Assign Organization Owner
**Statement**: Authorized users can assign Organization Owner role to users within the organization.
**Priority**: Critical
- **Actors**: SaaS Administrator, Account Owner, Account Admin.
- **Dependencies**: `USER-MANAGEMENT`, `ROLE-AND-PERMISSION-MANAGEMENT`

**Acceptance Scenarios**:
1. **Happy Path:** Given Account Owner assigns organization owner, When target user is member of organization, Then ownership is assigned successfully.
2. **Non-member:** Given Account Owner tries to assign owner to non-member, When they submit, Then 400 error with membership details is returned.
3. **Previous owner:** Given organization owner is assigned, When previous owner accesses organization, Then they retain other roles but lose owner privileges.

### REQ-ORG-008: Transfer Organization Ownership
**Statement**: Organization Owner can transfer ownership to another user within the organization.
**Priority**: High
- **Actors**: Organization Owner.
- **Dependencies**: `USER-MANAGEMENT`

**Acceptance Scenarios**:
1. **Happy Path:** Given Organization Owner transfers ownership, When target user is member of organization, Then ownership is transferred successfully.
2. **Non-member:** Given Organization Owner tries to transfer to non-member, When they submit, Then 400 error with membership details is returned.
3. **Previous owner:** Given ownership is transferred, When previous owner accesses organization, Then they retain other roles but lose owner privileges.

---

## 6. Error Handling

### Error Messages
- `ORGANIZATION_NOT_FOUND`: Organization does not exist or has been deleted
- `INSUFFICIENT_PERMISSIONS`: User lacks required permissions for operation
- `ORGANIZATION_NAME_EXISTS`: Organization name already exists in the account
- `INVALID_ORGANIZATION_DATA`: Organization data validation failed
- `ORGANIZATION_HAS_ACTIVE_SUBSCRIPTIONS`: Cannot deactivate/delete organization with active subscriptions
- `ORGANIZATION_CREATION_FAILED`: Organization creation process failed
- `ORGANIZATION_UPDATE_FAILED`: Organization update process failed
- `USER_NOT_ORGANIZATION_MEMBER`: Target user is not a member of the organization
- `ALREADY_ORGANIZATION_OWNER`: User is already the organization owner
- `INVALID_LOGO_URL`: Logo URL is invalid or inaccessible

### Retry Logic
- Organization creation: 2 retries with exponential backoff
- Organization updates: 1 retry with linear backoff
- Permission checks: No retry, immediate failure
- Database operations: 3 retries with exponential backoff
- Logo URL validation: 1 retry with linear backoff

### Idempotency
- Organization creation: Use unique name validation within account to prevent duplicates
- Organization updates: Check current state before applying changes
- Organization deletion: Check deletion status before processing
- Owner assignment: Check current ownership before assigning

---

## 7. Security & Audit

### Authentication
- All organization operations require valid authentication token
- API keys supported for programmatic access
- Session-based authentication for web access
- Multi-factor authentication required for organization deletion

### Authorization
- Organization-level permissions checked on every operation
- SaaS Administrator has full access to all organizations
- Account Owner has full access to organizations in their account
- Organization Owner has full access to their organization only
- SaaS Account Manager has read access to organizations in assigned accounts only

### Input Validation
- Organization name validation against allowed characters and length
- Logo URL format validation and accessibility check
- SQL injection prevention for all text inputs
- XSS prevention for display fields

### Rate Limiting
- 20 organization creations per Account Owner per hour
- 100 organization updates per user per hour
- 1000 organization reads per user per hour
- 10 organization deletions per Account Owner per day
- 50 owner assignments per Account Owner per hour

### Audit Logging
- All organization operations logged with user, timestamp, and action
- Organization access attempts logged with success/failure
- Permission changes logged with grantor and grantee
- Ownership transfers logged with previous and new owner details
- Sensitive data (logo URL) masked in logs

### Data Protection
- Organization data encrypted at rest using AES-256
- Logo URLs hashed for privacy
- Soft delete preserves data for compliance (7 years)
- Organization content not logged in audit trails

---

## 8. Open Questions / Risks / Decisions

### Open Questions
1. **Organization Naming Convention**: Should there be a standardized naming convention for organizations within accounts?
2. **Organization Hierarchy**: Should organizations support hierarchical structures (parent-child relationships)?
3. **Organization Merging**: Should there be a process to merge organizations within the same account?
4. **Organization Archiving**: Should inactive organizations be archived instead of deleted?
5. **Multi-Region Organizations**: How should organizations be handled across different geographic regions?
6. **Organization Templates**: Should there be predefined organization templates for common business units?

### Risks
1. **Data Isolation**: Risk of data leakage between organizations if permissions are misconfigured
2. **Organization Proliferation**: Risk of creating too many organizations without proper governance
3. **Compliance**: Risk of not meeting data retention requirements for deleted organizations
4. **Performance**: Risk of slow organization operations as the number of organizations grows
5. **Security**: Risk of unauthorized organization access if authentication is compromised
6. **Ownership Transfer**: Risk of losing organization control if ownership transfer fails

### Decisions
1. **Soft Delete**: Implemented for data recovery and compliance requirements
2. **Unique Constraints**: Organization name must be unique within account
3. **Permission Model**: Role-based access control with explicit permissions
4. **Audit Trail**: Comprehensive logging of all organization operations
5. **No Organization Sharing**: Each organization belongs to one account only
6. **Retention Policy**: Deleted organizations retained for 7 years for compliance
7. **Single Owner**: Only one Organization Owner per organization at a time
8. **Logo URL Validation**: Logo URLs must be accessible and valid

---

## Change Log

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0.0 | 2025-09-20 | Initial version migrated from legacy documents | AI Agent |
| 1.1.0 | 2025-01-27 | Added Error Handling, Security & Audit, and Open Questions/Risks/Decisions sections; removed Configurable Subscription Attributes and Predefined Custom Roles sections; fixed empty Constraints column in Exposed Permissions | AI Agent |
