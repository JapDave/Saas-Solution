# SUBSCRIPTION-MANAGEMENT — Subscription Management

> **Module Requirements File**
> **Core Module for managing module subscriptions with configurable attributes and permission control**

---

## Module Meta & Overview

**Owner:** Platform Engineering Team
**Version:** 1.0.0
**Last Updated:** 2025-01-27

**Purpose:** Provide comprehensive subscription management capabilities across all products in the platform. Enable organizations to subscribe to modules with configurable attributes, track usage against limits, and manage subscription lifecycle with proper permission control.

**Scope:** Module subscription CRUD operations, available modules discovery, configurable attributes validation, usage tracking, and subscription lifecycle management. Covers all subscription statuses and transitions.

**Cross-Product Impact:** All products can leverage subscription management capabilities. Subscription system is foundational and controls feature availability consistently across the entire platform.

---

## Dependencies

**Core Modules:**
- [AUTHENTICATION-AND-AUTHORIZATION](../CORE-MODULES/AUTHENTICATION-AND-AUTHORIZATION.md) - User authentication for subscription operations
- [ORGANIZATION-MANAGEMENT](../CORE-MODULES/ORGANIZATION-MANAGEMENT.md) - Organization-level subscription policies
- [PRODUCTS-AND-MODULES-MANAGEMENT](../CORE-MODULES/PRODUCTS-AND-MODULES-MANAGEMENT.md) - Module definitions and product relationships
- [USER-MANAGEMENT](../CORE-MODULES/USER-MANAGEMENT.md) - User assignment and subscription access

**Dependency Notes:** Subscription management is foundational and must be available before other modules that require subscription-based feature gating.

---

## 1. Data Model

### 1.1 Entity: Subscription
**Fields:**
- `id`: UUID, required, unique identifier
- `organizationId`: UUID, required, references `Organization.id`
- `moduleId`: UUID, required, references `DefinedModule.id`
- `status`: enum, required, [active, expired, suspended, cancelled, trial, archived], default: active
- `configuration`: JSON, required, module-specific configuration attributes
- `startDate`: timestamp, required, ISO 8601, subscription start time
- `endDate`: timestamp, optional, ISO 8601, subscription end time
- `trialEndDate`: timestamp, optional, ISO 8601, trial period end
- `createdBy`: UUID, required, references `User.id`
- `createdAt`: timestamp, required, ISO 8601, creation time
- `updatedAt`: timestamp, required, ISO 8601, last modification
- `deletedAt`: timestamp, optional, ISO 8601, deletion time

**Ownership/Visibility:** Subscriptions belong to organizations. Users can access subscription information based on their role and organizational scope. Deleted subscriptions are soft-deleted and retained for 7 years.

**Relationships:**
- Subscription → Organization: belongs_to (organization owns subscription)
- Subscription → DefinedModule: references (module being subscribed to)
- Subscription → User: created_by (user who created subscription)

---

## 2. Input Validation

### 2.1 Field-Level Rules
- `organizationId`: Must reference existing active organization
- `moduleId`: Must reference existing defined module that is subscribable
- `status`: Must be valid status with proper transition rules
- `configuration`: Must match module's configurable attributes schema
- `startDate`: Must be valid timestamp, cannot be in the past
- `endDate`: Must be after startDate if provided

### 2.2 Cross-Field Constraints
- If `status` is "trial", `trialEndDate` must be provided and after `startDate`
- If `status` is "expired", `endDate` must be provided and in the past
- Configuration attributes must match module's defined configurable attributes
- Organization cannot have multiple active subscriptions to the same module

### 2.3 Business Rules
- Users can only create subscriptions for organizations they have access to
- Only SaaS Administrators and SaaS Account Managers can create subscriptions
- Module must be subscribable (not core modules like Organization Management)
- Configuration values must be within defined ranges and limits
- Subscription status transitions must follow valid state machine

---

## 3. Workflows & States

### 3.1 State Machine
```
Trial → Active → Suspended → Cancelled
  ↓       ↓         ↓
Expired ← Expired ← Expired
  ↓
Archived
```

### 3.2 Allowed Actions by State
| State | Allowed Actions | Who Can Perform | Notes |
|-------|----------------|-----------------|-------|
| Trial | activate, cancel, expire | admin, system | Trial period |
| Active | suspend, cancel, expire | admin, system | Normal subscription |
| Suspended | reactivate, cancel, expire | admin, system | Temporarily disabled |
| Cancelled | archive, expire | admin, system | Permanently cancelled |
| Expired | reactivate, archive | admin, system | Past end date |
| Archived | none | system | Historical record |

### 3.3 Workflow Steps
1. **Subscription Creation**
   - Trigger: Admin creates new module subscription
   - Steps: Validate permissions → Check module availability → Validate configuration → Create subscription → Archive old subscription
   - Alternates: Module not available → Configuration invalid → Permission denied
   - Errors: Invalid module → Configuration error → Duplicate subscription

2. **Status Transition**
   - Trigger: Admin changes subscription status
   - Steps: Validate transition → Check business rules → Update status → Log transition
   - Alternates: Invalid transition → Business rule violation → Permission denied
   - Errors: Invalid status → Transition not allowed → Insufficient permissions

---

## 4. Exposed Permissions

| Permission Key | Scope | Description | Enforcement Points | Constraints |
|----------------|-------|-------------|-------------------|-------------|
| `subscriptions:create` | org | Create module subscriptions | Subscription creation | Admin permissions |
| `subscriptions:read` | org/team/user | Read subscription information | Subscription access | Role-based access |
| `subscriptions:update` | org | Update subscription status | Status changes | Admin permissions |
| `subscriptions:delete` | org | Delete subscriptions | Subscription deletion | Admin permissions |
| `subscriptions:admin` | org | Full subscription management | All operations | Admin permissions |
| `modules:list` | org | List available modules | Module discovery | Subscription context |

**Permission Notes:** Subscription permissions are managed through the Role & Permission Management module. Only SaaS Administrators and SaaS Account Managers can create and modify subscriptions.

---

## 5. Configurable Subscription Attributes

**Concept:** Configurable subscription attributes are module-specific settings that control feature availability, usage limits, and behavior within each subscribed module. These attributes are defined in each module's specification document according to the module template.

**Examples of Configurable Attributes:**
- `maxNumberOfTeams`: Maximum number of teams allowed (Teams module)
- `maxUserSeats`: Maximum number of user seats (User Management module)
- `maxFileSize`: Maximum file size for uploads (Files module)
- `maxStorageQuota`: Maximum storage quota in bytes (Files module)
- `retentionDays`: Data retention period in days (various modules)

**Attribute Definition Process:**
1. Each module defines its configurable attributes in its module specification
2. Attributes include type, min/max values, enforcement points, and overage policies
3. Subscription creation validates configuration against module definitions
4. Runtime enforcement checks current usage against configured limits

**Subscription Notes:** Configuration attributes are validated against module definitions during subscription creation. Runtime enforcement ensures organizations stay within their subscribed limits.

---

## 6. Predefined Custom Roles

**Note:** This module does not define predefined custom roles as subscription management is primarily an administrative function handled by SaaS Administrators and SaaS Account Managers.

---

## 7. Requirements

---

### REQ-SUBSCRIPTION-001: Get Available Modules for Product
**Statement:** Authorized users can retrieve available modules for a specific product with proper filtering and validation.

**Priority:** Critical

**Details:**
- **Purpose:** Allow users to discover which modules are available for subscription for a specific product
- **Actors & Access:** SaaS Administrator, SaaS Account Manager, Account Owner, Account Admin, Organization Owner, Organization Admin
- **Trigger:** User wants to create subscriptions for a product
- **Steps:**
  1. Validate user authentication and permissions
  2. Retrieve product definition from Products and Modules Management
  3. Retrieve module definitions for the product
  4. Filter out non-subscribable modules (core modules)
  5. Return available modules with configurable attributes
- **Data touched/created:** Module access logs
- **Rules & variations:** Product validation, module filtering, permission checking
- **Errors & fallbacks:** Product not found, insufficient permissions, module unavailable
- **Performance & limits:** Module list retrieval within 200ms
- **Security & audit:** Permission validation, access logging
- **Dependencies:** Products and Modules Management, Authentication, Authorization
- **Cross-product impact:** Module discovery available across all products

**Acceptance Scenarios:**
1. **List Modules:** Given Organization Owner requests available modules for Agents Platform, When they access endpoint, Then all subscribable modules are returned
2. **Product Not Found:** Given user requests modules for non-existent product, When they submit request, Then 404 error is returned
3. **Permission Denied:** Given user without permissions requests modules, When they submit request, Then 403 error is returned
4. **Filtered Results:** Given product with mixed module types, When user requests modules, Then only subscribable modules are returned

---

### REQ-SUBSCRIPTION-002: Create Module Subscription
**Statement:** SaaS Administrator and SaaS Account Manager can create module subscriptions for organizations with proper validation.

**Priority:** Critical

**Details:**
- **Purpose:** Create individual module subscriptions with configurable attributes and proper validation
- **Actors & Access:** SaaS Administrator, SaaS Account Manager
- **Trigger:** Organization needs access to a specific module
- **Steps:**
  1. Validate user permissions for subscription creation
  2. Validate organization exists and is active
  3. Validate module exists and is subscribable
  4. Validate configuration attributes against module definition
  5. Check for existing active subscription to same module
  6. Archive existing subscription if present
  7. Create new subscription record
  8. Log subscription creation event
- **Data touched/created:** Subscription entity, audit logs
- **Rules & variations:** Module validation, configuration validation, subscription limits
- **Errors & fallbacks:** Invalid module, configuration error, duplicate subscription
- **Performance & limits:** Subscription creation within 500ms
- **Security & audit:** Permission validation, configuration validation, audit logging
- **Dependencies:** Organization Management, Products and Modules Management, Authentication
- **Cross-product impact:** Subscription creation affects feature availability across all products

**Acceptance Scenarios:**
1. **Create Subscription:** Given SaaS Administrator creates subscription with valid configuration, When they submit, Then subscription is created successfully
2. **Duplicate Subscription:** Given existing active subscription, When admin creates new subscription, Then old subscription is archived and new one is created
3. **Invalid Configuration:** Given invalid configuration attributes, When admin creates subscription, Then creation is rejected with validation errors
4. **Permission Denied:** Given user without create permissions, When they attempt creation, Then access is denied

---

### REQ-SUBSCRIPTION-003: Retrieve Module Subscription Information
**Statement:** Authorized users can retrieve module subscription information based on their role and organizational scope.

**Priority:** Critical

**Details:**
- **Purpose:** Allow users to view subscription details they have access to with proper data filtering
- **Actors & Access:** SaaS Administrator, SaaS Account Manager, Account Owner, Account Admin, Organization Owner, Organization Admin
- **Trigger:** User requests subscription information
- **Steps:**
  1. Validate user authentication and permissions
  2. Check subscription existence and status
  3. Evaluate user permissions for subscription access
  4. Filter subscription data based on user scope
  5. Return filtered subscription information
- **Data touched/created:** Subscription access logs
- **Rules & variations:** Permission hierarchy, data filtering, scope limitations
- **Errors & fallbacks:** Subscription not found, insufficient permissions, access denied
- **Performance & limits:** Subscription retrieval within 100ms
- **Security & audit:** Permission validation, access logging, data filtering
- **Dependencies:** Authentication, Authorization modules
- **Cross-product impact:** Subscription access consistent across all products

**Acceptance Scenarios:**
1. **View Subscription:** Given Organization Owner requests subscription details, When they access their organization's subscription, Then subscription information is returned
2. **Cross-Organization:** Given Organization Owner tries to view different organization's subscription, When they request details, Then 403 forbidden error is returned
3. **SaaS Admin Access:** Given SaaS Administrator requests subscription details, When they access any subscription, Then full subscription information is returned
4. **Subscription Not Found:** Given non-existent subscription ID, When user requests details, Then 404 error is returned

---

### REQ-SUBSCRIPTION-004: Update Module Subscription Status
**Statement:** SaaS Administrator and SaaS Account Manager can update module subscription status with proper validation.

**Priority:** High

**Details:**
- **Purpose:** Change module subscription status with proper transition validation and business rules
- **Actors & Access:** SaaS Administrator, SaaS Account Manager
- **Trigger:** Subscription status needs to be changed
- **Steps:**
  1. Validate user permissions for status updates
  2. Validate new status is valid transition from current status
  3. Check business rules for status transition
  4. Update subscription status
  5. Log status transition event
  6. Trigger any necessary side effects
- **Data touched/created:** Subscription entity (status updated), audit logs
- **Rules & variations:** Status transition validation, business rule checking, side effects
- **Errors & fallbacks:** Invalid transition, business rule violation, permission denied
- **Performance & limits:** Status update within 200ms
- **Security & audit:** Permission validation, transition logging, audit trail
- **Dependencies:** Subscription access control, business rules
- **Cross-product impact:** Status changes immediately affect feature availability across all products

**Acceptance Scenarios:**
1. **Update Status:** Given SaaS Administrator updates subscription to suspended, When they submit, Then status is updated and organization loses module access
2. **Invalid Transition:** Given invalid status transition, When admin attempts update, Then 400 error with valid transitions is returned
3. **Business Rule Violation:** Given business rule prevents transition, When admin attempts update, Then 400 error with rule details is returned
4. **Permission Denied:** Given user without update permissions, When they attempt update, Then access is denied

---

### REQ-SUBSCRIPTION-005: Archive Module Subscription
**Statement:** System automatically archives module subscriptions based on various triggers with proper validation.

**Priority:** Medium

**Details:**
- **Purpose:** Archive old module subscriptions when new ones are created or other conditions are met
- **Actors & Access:** System (automatic)
- **Trigger:** New subscription created for same module, subscription cancellation, or other business rules
- **Steps:**
  1. System detects archiving trigger
  2. Validate archiving conditions are met
  3. Set old subscription status to archived
  4. Log archiving event
  5. Return archiving confirmation
- **Data touched/created:** Subscription entity (status set to archived), audit logs
- **Rules & variations:** Archiving triggers, condition validation, automatic operation
- **Errors & fallbacks:** Cannot archive active subscription, archiving conditions not met
- **Performance & limits:** Archiving operation within 300ms
- **Security & audit:** System operation logging, archiving audit
- **Dependencies:** Subscription creation, business rules
- **Cross-product impact:** Archiving affects historical subscription records across all products

**Acceptance Scenarios:**
1. **Auto-Archive:** Given new subscription created for same module, When system processes request, Then old subscription is automatically archived
2. **Manual Archive:** Given admin attempts to archive active subscription, When they submit, Then 400 error with explanation is returned
3. **Archive Confirmation:** Given subscription is archived, When user tries to access archived subscription, Then access is denied
4. **Multiple Archives:** Given multiple old subscriptions, When new subscription is created, Then all old subscriptions are archived

---

### REQ-SUBSCRIPTION-006: List Module Subscriptions with Pagination
**Statement:** Authorized users can retrieve paginated list of module subscriptions they have access to.

**Priority:** High

**Details:**
- **Purpose:** Allow users to browse and search module subscriptions within their scope with pagination
- **Actors & Access:** SaaS Administrator, SaaS Account Manager, Account Owner, Account Admin, Organization Owner, Organization Admin
- **Trigger:** User requests subscription list
- **Steps:**
  1. Validate user permissions for subscription listing
  2. Retrieve filtered subscription list based on user scope
  3. Apply pagination parameters
  4. Return paginated results with metadata
- **Data touched/created:** Subscription access logs
- **Rules & variations:** Scope filtering, pagination limits, sorting options
- **Errors & fallbacks:** Invalid pagination parameters, insufficient permissions
- **Performance & limits:** Subscription list retrieval within 200ms, max 100 subscriptions per page
- **Security & audit:** Permission validation, access logging
- **Dependencies:** Subscription access control
- **Cross-product impact:** Subscription listing available across all products

**Acceptance Scenarios:**
1. **List Subscriptions:** Given Organization Owner requests subscription list, When they access endpoint, Then paginated subscriptions are returned
2. **SaaS Admin List:** Given SaaS Administrator requests subscription list, When they access endpoint, Then all subscriptions are returned
3. **Invalid Pagination:** Given invalid page parameters, When user requests list, Then error is returned
4. **Empty Results:** Given no accessible subscriptions, When user requests list, Then empty list is returned

---

### REQ-SUBSCRIPTION-007: Validate Module Configuration Attributes
**Statement:** System validates module subscription configuration against module definition with comprehensive validation.

**Priority:** Critical

**Details:**
- **Purpose:** Ensure module subscription configurations are valid and complete according to module specifications
- **Actors & Access:** System (internal validation service)
- **Trigger:** Module subscription creation or update
- **Steps:**
  1. Receive configuration data and module ID
  2. Retrieve module configuration schema from module definition
  3. Validate all required attributes are present
  4. Validate attribute values are within allowed ranges
  5. Validate attribute types match expected types
  6. Return comprehensive validation result
- **Data touched/created:** Validation logs
- **Rules & variations:** Schema validation, type checking, range validation
- **Errors & fallbacks:** Invalid attributes, missing required fields, type mismatches
- **Performance & limits:** Configuration validation within 100ms
- **Security & audit:** Input validation, validation logging
- **Dependencies:** Products and Modules Management, module definitions
- **Cross-product impact:** Configuration validation ensures consistent behavior across all products

**Acceptance Scenarios:**
1. **Valid Configuration:** Given valid configuration is provided, When system validates, Then validation passes
2. **Invalid Configuration:** Given invalid configuration is provided, When system validates, Then validation fails with specific error messages
3. **Missing Attributes:** Given missing required attributes, When system validates, Then validation fails with missing attribute list
4. **Type Mismatch:** Given wrong attribute types, When system validates, Then validation fails with type error messages

---

### REQ-SUBSCRIPTION-008: Track Module Usage Against Configuration
**Statement:** System tracks resource usage against module subscription configuration limits with real-time enforcement.

**Priority:** High

**Details:**
- **Purpose:** Monitor usage against module subscription limits and prevent overages with proper enforcement
- **Actors & Access:** System (internal usage tracking service)
- **Trigger:** Resource creation or modification within a module
- **Steps:**
  1. Receive resource creation request with organization and module context
  2. Retrieve organization's active module subscription
  3. Check current usage against configuration limits
  4. Validate if resource creation is allowed
  5. Allow or deny resource creation
  6. Update usage counters if creation is allowed
- **Data touched/created:** Usage tracking logs, resource creation records
- **Rules & variations:** Real-time enforcement, usage limits, overage policies
- **Errors & fallbacks:** Usage limit exceeded, no active subscription, tracking failure
- **Performance & limits:** Usage check within 50ms
- **Security & audit:** Usage validation, tracking logging
- **Dependencies:** Subscription management, module-specific usage tracking
- **Cross-product impact:** Usage tracking affects resource creation across all products

**Acceptance Scenarios:**
1. **Within Limits:** Given organization within subscription limits, When user creates resource, Then creation is allowed
2. **Limit Exceeded:** Given organization at subscription limit, When user tries to create resource, Then creation is rejected with limit error
3. **No Subscription:** Given organization without active subscription, When user tries to create resource, Then creation is rejected with subscription error
4. **Usage Update:** Given resource is created, When system processes creation, Then usage counters are updated

---

## 8. Error Handling

### Error Messages
- `SUBSCRIPTION_NOT_FOUND`: Subscription does not exist or has been deleted
- `INSUFFICIENT_PERMISSIONS`: User lacks required permissions for operation
- `INVALID_MODULE`: Module not found or not subscribable
- `INVALID_CONFIGURATION`: Configuration attributes are invalid or incomplete
- `DUPLICATE_SUBSCRIPTION`: Organization already has active subscription to module
- `INVALID_STATUS_TRANSITION`: Status transition is not allowed
- `USAGE_LIMIT_EXCEEDED`: Resource creation exceeds subscription limits
- `ORGANIZATION_NOT_FOUND`: Organization does not exist or is inactive

### Retry Logic
- Subscription creation failures: 3 retries with exponential backoff
- Status update failures: 2 retries with linear backoff
- Usage tracking failures: 3 retries with exponential backoff

### Idempotency
- Subscription creation: Use organization-module combination for deduplication
- Status updates: Check current status before updating
- Usage tracking: Use atomic counters for consistency

---

## 9. Security & Audit

### Authentication
- All subscription operations require valid authentication token
- API keys supported for programmatic access
- Session-based authentication for web access

### Authorization
- Subscription-level permissions checked on every operation
- Organization and user permissions inherited
- SaaS Administrator and SaaS Account Manager roles required for creation/modification

### Input Validation
- Configuration validation against module schemas
- Status transition validation against state machine
- Organization and module existence validation
- Usage limit validation against subscription configuration

### Rate Limiting
- 20 subscription operations per user per hour
- 100 usage tracking requests per organization per hour
- 50 configuration validation requests per user per hour

### Audit Logging
- All subscription operations logged with user, timestamp, and action
- Status transitions logged with before/after values
- Usage tracking logged for monitoring and billing
- Configuration changes logged with validation results

### Data Protection
- Subscription data encrypted at rest using AES-256
- Configuration data masked in logs for security
- Sensitive subscription information redacted in audit trails
- Usage data retained for billing and analytics

---

## 10. Acceptance Scenarios

### Subscription Creation Scenarios
1. **Successful Creation**
   - Given: SaaS Administrator with create permissions
   - When: Admin creates subscription with valid configuration
   - Then: Subscription is created and active
   - And: Organization gains module access

2. **Configuration Validation**
   - Given: Invalid configuration attributes
   - When: Admin creates subscription
   - Then: Creation is rejected with validation errors
   - And: Admin is shown valid configuration format

3. **Duplicate Subscription**
   - Given: Existing active subscription to module
   - When: Admin creates new subscription
   - Then: Old subscription is archived and new one is created
   - And: Organization maintains module access

### Status Transition Scenarios
1. **Suspend Subscription**
   - Given: Active subscription
   - When: Admin suspends subscription
   - Then: Status is updated to suspended
   - And: Organization loses module access

2. **Invalid Transition**
   - Given: Cancelled subscription
   - When: Admin tries to activate
   - Then: Transition is rejected with error
   - And: Admin is shown valid transitions

3. **Expire Subscription**
   - Given: Subscription past end date
   - When: System processes expiration
   - Then: Status is updated to expired
   - And: Organization loses module access

---

## 11. Open Questions / Risks / Decisions

### Open Questions
All open questions have been resolved:
1. Subscription pricing: Not handled by this module, delegated to billing system
2. Usage billing: Not handled by this module, delegated to billing system
3. Subscription renewals: Not handled by this module, delegated to billing system
4. Multi-tenant subscriptions: Not supported, one subscription per organization per module

### Risks
1. **Configuration Complexity**: Complex configuration validation could impact performance
2. **Usage Tracking**: Real-time usage tracking could become a bottleneck
3. **Status Management**: Complex status transitions could lead to inconsistent states

### Decisions
1. **Single Active Subscription**: Only one active subscription per organization per module
2. **Automatic Archiving**: Old subscriptions are automatically archived when new ones are created
3. **Real-time Enforcement**: Usage limits are enforced in real-time for security
4. **Configuration Validation**: All configurations are validated against module schemas
5. **Status State Machine**: Strict state machine for subscription status transitions
6. **Soft Delete**: Implemented for subscription recovery and compliance

---

## Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2025-01-27 | Initial version | Requirements Team |
