# ACCOUNT-MANAGEMENT — Account Management

> **Module Requirements File**
> **Core Module for managing top-level enterprise customer accounts with multi-organization support**

---

## Module Meta & Overview

**Module Type:** Core

**Owner:** SaaS Platform Team

**Version:** 1.0.0

**Last Updated:** 2025-09-20

**Purpose:** Manage top-level enterprise customer accounts with multi-organization support.

**Scope:** Account CRUD operations, lifecycle management, and enterprise-level administration.

**Success Criteria:** Support 1000+ enterprise accounts with complete data isolation.

**Cross-Product Impact:** Account management supports all current and future products (Agents Platform, One Inbox, DocVerse).

---

## Dependencies

**Core Modules:**
- [AUTHENTICATION-AND-AUTHORIZATION](../CORE-MODULES/AUTHENTICATION-AND-AUTHORIZATION.md) - For authenticating users making account management requests.
- [USER-MANAGEMENT](../CORE-MODULES/USER-MANAGEMENT.md) - Account ownership is tied to a user.

**Dependency Notes:** Account management is a foundational module.

---

## 1. Data Model

### 1.1 Entity: Account
**Fields:**
- `accountId`: integer, auto-generated, unique, required, example: 101, rules: primary key
- `name`: string, 1-100 chars, required, example: "Acme Corporation", rules: unique across platform
- `description`: text, max 500 chars, optional, example: "Enterprise customer account", rules: nullable
- `contactEmail`: string, valid email format, required, example: "admin@acmecorp.com", rules: unique across platform
- `isActive`: boolean, default true, required, example: true, rules: cannot be null
- `createdBy`: integer, required, example: 12345, rules: references User.userId
- `createdAt`: timestamp, auto-generated, required, example: "2025-01-01T00:00:00Z", rules: immutable
- `updatedAt`: timestamp, auto-generated, required, example: "2025-01-01T00:00:00Z", rules: updated on every change
- `deletedAt`: timestamp, nullable, example: null, rules: set on soft delete

**Ownership/Visibility:**
- SaaS Administrator: full read/write access to all accounts
- SaaS Account Manager: read access to assigned accounts only
- Account Owner: full read/write access to their account only
- Account Admin: read access to their account only
- Retention: soft-deleted accounts retained for 7 years for compliance
- Masking/redaction: contact email visible only to authorized users

**Relationships:**
- Account → Organization: one-to-many (an account can have multiple organizations)
- Account → User: many-to-one (the `createdBy` user)

---

## 2. Input Validation

### 2.1 Field-Level Rules
- `name`: required, string, 1-100 chars, unique.
- `description`: optional, text, max 500 chars.
- `contactEmail`: required, valid email format, unique.

### 2.2 Cross-Field Constraints
- None

### 2.3 Business Rules
- Account name must be unique across the platform.
- Contact email must be unique across the platform.

---

## 3. Workflows & States

### 3.1 State Machine
```
Active → Inactive → Deleted
```

### 3.2 Allowed Actions by State
| State | Allowed Actions | Who Can Perform | Notes |
|---|---|---|---|
| Active | update, deactivate, delete, list, get | SaaS Admin, Account Owner | Normal state |
| Inactive | activate | SaaS Admin, Account Owner | Account is disabled |
| Deleted | none | - | Soft-deleted, retained for compliance |

### 3.3 Workflow Steps
**1. Account Deactivation**
   - Trigger: User with permission deactivates an account.
   - Steps:
     1. Check if the account has active subscriptions.
     2. If not, set `isActive` to `false`.
     3. Log the deactivation event.
   - Errors: Account has active subscriptions.

---

## 4. Exposed Permissions
| Permission Key | Scope | Description | Enforcement Points | Constraints |
|---|---|---|---|---|
| `account:create` | platform | Create a new enterprise account | Account creation endpoint | SaaS Administrator only |
| `account:read` | account | Read account information | Account retrieval endpoint | Account Owner, Account Admin, SaaS Account Manager (assigned accounts only) |
| `account:update` | account | Update account information | Account update endpoint | Account Owner, SaaS Administrator |
| `account:delete` | platform | Delete an account | Account deletion endpoint | SaaS Administrator only |
| `account:list` | platform | List all accounts | Account list endpoint | SaaS Administrator, SaaS Account Manager (assigned accounts only) |

---

---

## 5. Requirements

### REQ-ACCOUNT-001: Create Enterprise Account
**Statement**: SaaS Administrator can create a new enterprise account with required information.
**Priority**: Critical
**Details**:
- **Purpose**: Onboard new enterprise customers to the platform.
- **Actors & Access**: SaaS Administrator only.
- **Trigger**: New enterprise customer signs up or is manually onboarded.
- **Steps**:
  1. SaaS Administrator provides account details.
  2. System validates account information.
  3. System creates account record.
  4. System creates audit log entry.
  5. System returns account details.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **Happy Path:** Given SaaS Administrator is authenticated, When they create account with valid data, Then account is created successfully with unique ID.
2. **Duplicate Name:** Given SaaS Administrator tries to create account with duplicate name, When they submit, Then system returns 409 conflict error.
3. **Audit:** Given SaaS Administrator creates account, When system processes request, Then audit log entry is created with creation details.

### REQ-ACCOUNT-002: Retrieve Account Information
**Statement**: Authorized users can retrieve account information based on their role and scope.
**Priority**: Critical
**Details**:
- **Purpose**: Allow users to view account details they have access to.
- **Actors & Access**: SaaS Administrator, SaaS Account Manager, Account Owner, Account Admin.
- **Trigger**: User requests account information.
- **Steps**:
  1. User requests account details.
  2. System validates user permissions.
  3. System retrieves account information.
  4. System returns filtered account data.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **SaaS Admin:** Given SaaS Administrator requests account details, When they access any account, Then full account information is returned.
2. **Account Owner:** Given Account Owner requests their account details, When they access their account, Then account information is returned.
3. **Unauthorized:** Given Account Owner tries to access a different account, When they request details, Then 403 forbidden error is returned.

### REQ-ACCOUNT-003: Update Account Information
**Statement**: Authorized users can update account information within their scope.
**Priority**: High
**Details**:
- **Purpose**: Allow account information to be modified as needed.
- **Actors & Access**: SaaS Administrator, Account Owner.
- **Trigger**: Account information needs to be updated.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **Happy Path:** Given Account Owner updates their account name, When they submit valid data, Then account is updated successfully.
2. **Unauthorized:** Given Account Owner tries to update a different account, When they submit, Then 403 forbidden error is returned.
3. **Email Validation:** Given Account Owner updates contact email, When they submit, Then email validation is performed.

### REQ-ACCOUNT-004: Deactivate Account
**Statement**: Authorized users can deactivate accounts to prevent access while preserving data.
**Priority**: High
**Details**:
- **Purpose**: Temporarily disable account access without data loss.
- **Actors & Access**: SaaS Administrator, Account Owner.
- **Trigger**: Account needs to be temporarily disabled.
- **Dependencies**: `SUBSCRIPTION-MANAGEMENT`

**Acceptance Scenarios**:
1. **Happy Path:** Given Account Owner deactivates their account, When account has no active subscriptions, Then account is deactivated successfully.
2. **With Subscriptions:** Given Account Owner tries to deactivate account with active subscriptions, When they submit, Then 400 error with subscription details is returned.
3. **SaaS Admin:** Given SaaS Administrator deactivates any account, When they submit, Then account is deactivated regardless of subscription status.

### REQ-ACCOUNT-005: Delete Account (Soft Delete)
**Statement**: SaaS Administrator can soft delete accounts for data retention compliance.
**Priority**: Medium
**Details**:
- **Purpose**: Remove accounts from active use while preserving data for compliance.
- **Actors & Access**: SaaS Administrator only.
- **Trigger**: Account needs to be permanently removed.
- **Dependencies**: `SUBSCRIPTION-MANAGEMENT`

**Acceptance Scenarios**:
1. **Happy Path:** Given SaaS Administrator deletes account with no active subscriptions, When they submit, Then account is soft deleted successfully.
2. **With Subscriptions:** Given SaaS Administrator tries to delete account with active subscriptions, When they submit, Then 400 error with subscription details is returned.
3. **Access after delete:** Given account is soft deleted, When any user tries to access it, Then 404 not found error is returned.

### REQ-ACCOUNT-006: List Accounts with Pagination
**Statement**: Authorized users can retrieve paginated list of accounts they have access to.
**Priority**: High
**Details**:
- **Purpose**: Allow users to browse and search accounts within their scope.
- **Actors & Access**: SaaS Administrator, SaaS Account Manager.
- **Trigger**: User requests account list.
- **Dependencies**: `AUTHENTICATION-AND-AUTHORIZATION`

**Acceptance Scenarios**:
1. **SaaS Admin:** Given SaaS Administrator requests account list, When they access endpoint, Then all accounts are returned with pagination.
2. **Account Manager:** Given SaaS Account Manager requests account list, When they access endpoint, Then only assigned accounts are returned.
3. **Invalid Pagination:** Given user requests account list with invalid page size, When they submit, Then 400 error with valid range is returned.

---

## 6. Error Handling

### Error Messages
- `ACCOUNT_NOT_FOUND`: Account does not exist or has been deleted
- `INSUFFICIENT_PERMISSIONS`: User lacks required permissions for operation
- `ACCOUNT_NAME_EXISTS`: Account name already exists in the platform
- `CONTACT_EMAIL_EXISTS`: Contact email already exists in the platform
- `ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS`: Cannot deactivate/delete account with active subscriptions
- `INVALID_ACCOUNT_DATA`: Account data validation failed
- `ACCOUNT_CREATION_FAILED`: Account creation process failed
- `ACCOUNT_UPDATE_FAILED`: Account update process failed

### Retry Logic
- Account creation: 2 retries with exponential backoff
- Account updates: 1 retry with linear backoff
- Permission checks: No retry, immediate failure
- Database operations: 3 retries with exponential backoff

### Idempotency
- Account creation: Use unique name/email validation to prevent duplicates
- Account updates: Check current state before applying changes
- Account deletion: Check deletion status before processing

---

## 7. Security & Audit

### Authentication
- All account operations require valid authentication token
- API keys supported for programmatic access
- Session-based authentication for web access
- Multi-factor authentication required for account deletion

### Authorization
- Account-level permissions checked on every operation
- SaaS Administrator has full access to all accounts
- Account Owner has full access to their account only
- SaaS Account Manager has read access to assigned accounts only

### Input Validation
- Account name validation against allowed characters and length
- Email format validation for contact email
- SQL injection prevention for all text inputs
- XSS prevention for display fields

### Rate Limiting
- 10 account creations per SaaS Administrator per hour
- 100 account updates per user per hour
- 1000 account reads per user per hour
- 5 account deletions per SaaS Administrator per day

### Audit Logging
- All account operations logged with user, timestamp, and action
- Account access attempts logged with success/failure
- Permission changes logged with grantor and grantee
- Sensitive data (contact email) masked in logs

### Data Protection
- Account data encrypted at rest using AES-256
- Contact email hashed for privacy
- Soft delete preserves data for compliance (7 years)
- Account content not logged in audit trails

---

## 8. Open Questions / Risks / Decisions

### Open Questions
1. **Account Naming Convention**: Should there be a standardized naming convention for enterprise accounts?
2. **Account Transfer**: How should account ownership be transferred between users?
3. **Account Merging**: Should there be a process to merge duplicate accounts?
4. **Account Archiving**: Should inactive accounts be archived instead of deleted?
5. **Multi-Region Support**: How should accounts be handled across different geographic regions?

### Risks
1. **Data Isolation**: Risk of data leakage between accounts if permissions are misconfigured
2. **Account Proliferation**: Risk of creating too many accounts without proper governance
3. **Compliance**: Risk of not meeting data retention requirements for deleted accounts
4. **Performance**: Risk of slow account operations as the number of accounts grows
5. **Security**: Risk of unauthorized account access if authentication is compromised

### Decisions
1. **Soft Delete**: Implemented for data recovery and compliance requirements
2. **Unique Constraints**: Account name and contact email must be unique across platform
3. **Permission Model**: Role-based access control with explicit permissions
4. **Audit Trail**: Comprehensive logging of all account operations
5. **No Account Sharing**: Each account belongs to one organization only
6. **Retention Policy**: Deleted accounts retained for 7 years for compliance

---

## Change Log

| Version | Date | Changes | Author |
|---|---|---|---|
| 1.0.0 | 2025-09-20 | Initial version migrated from legacy documents | AI Agent |
| 1.1.0 | 2025-01-27 | Added Error Handling, Security & Audit, and Open Questions/Risks/Decisions sections; removed Configurable Subscription Attributes and Predefined Custom Roles sections | AI Agent |
| 1.1.1 | 2025-01-27 | Fixed empty Constraints column in Exposed Permissions section | AI Agent |
