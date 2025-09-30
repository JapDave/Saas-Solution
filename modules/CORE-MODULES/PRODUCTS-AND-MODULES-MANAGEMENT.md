# PRODUCTS-AND-MODULES-MANAGEMENT — Products & Modules Management

> **Module Requirements File**
> **Core Module for managing the platform's products and their constituent modules**

---

## Module Meta & Overview

**Owner:** SaaS Platform Team
**Version:** 1.0.0
**Last Updated:** 2025-01-27

**Purpose:** Provide centralized definition and management of all products and modules available on the platform. Serve as the single source of truth for product composition, module capabilities, and subscription configuration.

**Scope:** Product definitions, module specifications, configurable attributes, exposed permissions, and product-module associations. Covers all subscribable and non-subscribable modules across the platform.

**Cross-Product Impact:** All products leverage this module for feature availability and subscription management. Product and module definitions are foundational and affect the entire platform.

---

## Dependencies

**Core Modules:**
- [SUBSCRIPTION-MANAGEMENT](../CORE-MODULES/SUBSCRIPTION-MANAGEMENT.md) - Module subscription management and configuration
- [AUTHENTICATION-AND-AUTHORIZATION](../CORE-MODULES/AUTHENTICATION-AND-AUTHORIZATION.md) - Access control for product/module management
- [ORGANIZATION-MANAGEMENT](../CORE-MODULES/ORGANIZATION-MANAGEMENT.md) - Organization-level product access

**Dependency Notes:** Products and modules management is foundational and must be available before subscription management can function properly.

---

## 1. Data Model

### 1.1 Entity: Product
**Fields:**
- `id`: integer, required, unique identifier
- `key`: string, required, unique key (e.g., "AGENTS_PLATFORM")
- `name`: string, required, 1-100 chars, display name
- `description`: text, required, 1-500 chars, product description
- `availableModuleKeys`: array[string], required, references Module.key
- `targetSegments`: array[string], optional, 0-10 segments, 1-50 chars each
- `useCases`: array[string], optional, 0-20 use cases, 1-100 chars each
- `isActive`: boolean, required, default true, product availability
- `createdAt`: timestamp, required, ISO 8601, creation time
- `updatedAt`: timestamp, required, ISO 8601, last modification

**Ownership/Visibility:** Products are platform-wide definitions. All authenticated users can view active products.

**Relationships:**
- Product → Module: many_to_many (products include multiple modules)

### 1.2 Entity: Module
**Fields:**
- `id`: integer, required, unique identifier
- `key`: string, required, unique key (e.g., "USER_MANAGEMENT")
- `code`: string, required, unique module code (e.g., "UM")
- `name`: string, required, 1-100 chars, display name
- `description`: text, optional, 0-500 chars, module description
- `subscribable`: boolean, required, default true, whether module can be subscribed to
- `configurableAttributes`: JSON, optional, module-specific configuration schema
- `exposedPermissions`: array[string], optional, 0-50 permissions, permission keys
- `isActive`: boolean, required, default true, module availability
- `createdAt`: timestamp, required, ISO 8601, creation time
- `updatedAt`: timestamp, required, ISO 8601, last modification

**Ownership/Visibility:** Modules are platform-wide definitions. All authenticated users can view active modules.

**Relationships:**
- Module → Product: many_to_many (modules can be included in multiple products)

---

## 2. Input Validation

### 2.1 Field-Level Rules
- `key`: Must be valid identifier, uppercase with underscores, 1-50 characters
- `code`: Must be valid identifier, uppercase letters only, 2-10 characters
- `name`: Must be valid display name, 1-100 characters
- `description`: Must be valid text, 0-500 characters
- `targetSegments`: Each segment must be 1-50 characters, max 10 segments
- `useCases`: Each use case must be 1-100 characters, max 20 use cases

### 2.2 Cross-Field Constraints
- Product key must be unique across all products
- Module key must be unique across all modules
- Module code must be unique across all modules
- Available module keys must reference existing active modules
- Subscribable modules must have configurable attributes defined

### 2.3 Business Rules
- Products must have at least one available module
- Non-subscribable modules cannot have configurable attributes
- Module permissions must be valid permission keys
- Product and module definitions are immutable (hardcoded)

---

## 3. Workflows & States

### 3.1 State Machine
```
Active → Inactive
  ↓
Deleted
```

### 3.2 Allowed Actions by State
| State | Allowed Actions | Who Can Perform | Notes |
|-------|----------------|-----------------|-------|
| Active | read, list | all authenticated users | Normal state |
| Inactive | read, list | all authenticated users | Disabled but visible |
| Deleted | none | system | Soft-deleted, retained for compliance |

### 3.3 Workflow Steps
1. **Product/Module Discovery**
   - Trigger: User requests available products or modules
   - Steps: Validate authentication → Filter active items → Return definitions
   - Alternates: No authentication → Invalid request
   - Errors: Authentication failed → Invalid parameters

---

## 4. Exposed Permissions

| Permission Key | Scope | Description | Enforcement Points | Constraints |
|----------------|-------|-------------|-------------------|-------------|
| `products:list` | platform | List all available products | Product listing endpoint | Authentication required |
| `products:read` | platform | Read product details | Product retrieval endpoint | Authentication required |
| `modules:list` | platform | List all available modules | Module listing endpoint | Authentication required |
| `modules:read` | platform | Read module details | Module retrieval endpoint | Authentication required |
| `modules:config_schema` | platform | Get module configuration schema | Configuration endpoint | Authentication required |

**Permission Notes:** Product and module definitions are read-only and available to all authenticated users. No write permissions as definitions are hardcoded.

---

## 5. Configurable Subscription Attributes

**Note:** This module does not define configurable subscription attributes as it manages the definitions of other modules' attributes. Each module defines its own configurable attributes in its specification.

---

## 6. Predefined Custom Roles

**Note:** This module does not define predefined custom roles as product and module definitions are read-only and available to all authenticated users.

---

## 7. Requirements

---

### REQ-PRODMOD-001: List Available Products
**Statement:** Authenticated users can retrieve a list of all available products with their associated modules.

**Priority:** Critical

**Details:**
- **Purpose:** Allow users to discover available products and their module compositions
- **Actors & Access:** All authenticated users
- **Trigger:** User requests product listing
- **Steps:**
  1. Validate user authentication
  2. Retrieve all active products
  3. Include associated module information
  4. Return product list with metadata
- **Data touched/created:** Product access logs
- **Rules & variations:** Active products only, include module details
- **Errors & fallbacks:** Authentication required, no products available
- **Performance & limits:** Product list retrieval within 100ms
- **Security & audit:** Authentication validation, access logging
- **Dependencies:** Authentication module
- **Cross-product impact:** Product discovery available across all products

**Acceptance Scenarios:**
1. **List Products:** Given authenticated user, When they request products, Then all active products are returned
2. **Unauthenticated:** Given unauthenticated user, When they request products, Then 401 error is returned
3. **Empty List:** Given no active products, When user requests products, Then empty list is returned

---

### REQ-PRODMOD-002: Get Product Details
**Statement:** Authenticated users can retrieve detailed information about a specific product including its modules.

**Priority:** Critical

**Details:**
- **Purpose:** Provide comprehensive product information for subscription decisions
- **Actors & Access:** All authenticated users
- **Trigger:** User requests specific product details
- **Steps:**
  1. Validate user authentication
  2. Validate product exists and is active
  3. Retrieve product details with module information
  4. Return comprehensive product data
- **Data touched/created:** Product access logs
- **Rules & variations:** Active products only, include all module details
- **Errors & fallbacks:** Product not found, product inactive
- **Performance & limits:** Product retrieval within 50ms
- **Security & audit:** Authentication validation, access logging
- **Dependencies:** Authentication module
- **Cross-product impact:** Product details available across all products

**Acceptance Scenarios:**
1. **Get Product:** Given authenticated user, When they request product details, Then product information is returned
2. **Product Not Found:** Given non-existent product, When user requests details, Then 404 error is returned
3. **Inactive Product:** Given inactive product, When user requests details, Then 404 error is returned

---

### REQ-PRODMOD-003: List Available Modules
**Statement:** Authenticated users can retrieve a list of all available modules with their configuration details.

**Priority:** Critical

**Details:**
- **Purpose:** Allow users to discover available modules and their subscription options
- **Actors & Access:** All authenticated users
- **Trigger:** User requests module listing
- **Steps:**
  1. Validate user authentication
  2. Retrieve all active modules
  3. Include configuration and permission details
  4. Return module list with metadata
- **Data touched/created:** Module access logs
- **Rules & variations:** Active modules only, include configuration schemas
- **Errors & fallbacks:** Authentication required, no modules available
- **Performance & limits:** Module list retrieval within 100ms
- **Security & audit:** Authentication validation, access logging
- **Dependencies:** Authentication module
- **Cross-product impact:** Module discovery available across all products

**Acceptance Scenarios:**
1. **List Modules:** Given authenticated user, When they request modules, Then all active modules are returned
2. **Unauthenticated:** Given unauthenticated user, When they request modules, Then 401 error is returned
3. **Empty List:** Given no active modules, When user requests modules, Then empty list is returned

---

### REQ-PRODMOD-004: Get Module Configuration Schema
**Statement:** Authenticated users can retrieve the configuration schema for subscribable modules.

**Priority:** High

**Details:**
- **Purpose:** Provide configuration schemas for subscription creation
- **Actors & Access:** All authenticated users
- **Trigger:** User requests module configuration schema
- **Steps:**
  1. Validate user authentication
  2. Validate module exists and is subscribable
  3. Retrieve module configuration schema
  4. Return configuration details
- **Data touched/created:** Module access logs
- **Rules & variations:** Subscribable modules only, include validation rules
- **Errors & fallbacks:** Module not found, module not subscribable
- **Performance & limits:** Schema retrieval within 50ms
- **Security & audit:** Authentication validation, access logging
- **Dependencies:** Authentication module
- **Cross-product impact:** Configuration schemas available across all products

**Acceptance Scenarios:**
1. **Get Schema:** Given subscribable module, When user requests schema, Then configuration schema is returned
2. **Non-Subscribable:** Given non-subscribable module, When user requests schema, Then 400 error is returned
3. **Module Not Found:** Given non-existent module, When user requests schema, Then 404 error is returned

---

## 8. Error Handling

### Error Messages
- `PRODUCT_NOT_FOUND`: Product does not exist or is inactive
- `MODULE_NOT_FOUND`: Module does not exist or is inactive
- `MODULE_NOT_SUBSCRIBABLE`: Module cannot be subscribed to
- `AUTHENTICATION_REQUIRED`: User must be authenticated to access definitions
- `INVALID_PRODUCT_KEY`: Product key is invalid or malformed
- `INVALID_MODULE_KEY`: Module key is invalid or malformed

### Retry Logic
- Product/module retrieval: No retry, immediate response
- Configuration schema retrieval: No retry, immediate response

### Idempotency
- All operations are read-only and idempotent
- No state changes require idempotency handling

---

## 9. Security & Audit

### Authentication
- All product and module operations require valid authentication token
- No anonymous access to product/module definitions
- Session-based authentication for web access

### Authorization
- Read-only access for all authenticated users
- No write permissions as definitions are hardcoded
- No role-based restrictions on reading definitions

### Input Validation
- Product and module key validation
- Parameter sanitization for search and filtering
- No user input for product/module definitions

### Rate Limiting
- 1000 product/module requests per user per hour
- 100 configuration schema requests per user per hour

### Audit Logging
- All product/module access logged with user and timestamp
- Configuration schema access logged for monitoring
- No sensitive data in audit trails

### Data Protection
- Product and module definitions are public information
- No encryption required for definition data
- Audit logs retained for compliance

---

## 10. Acceptance Scenarios

### Product Discovery Scenarios
1. **List All Products**
   - Given: Authenticated user
   - When: User requests product list
   - Then: All active products are returned with module information
   - And: Response includes product metadata

2. **Get Specific Product**
   - Given: Authenticated user with valid product key
   - When: User requests product details
   - Then: Product information is returned with all associated modules
   - And: Response includes target segments and use cases

3. **Product Not Found**
   - Given: Authenticated user with invalid product key
   - When: User requests product details
   - Then: 404 error is returned
   - And: Error message indicates product not found

### Module Discovery Scenarios
1. **List All Modules**
   - Given: Authenticated user
   - When: User requests module list
   - Then: All active modules are returned with configuration details
   - And: Response includes subscription information

2. **Get Module Configuration**
   - Given: Authenticated user with subscribable module
   - When: User requests configuration schema
   - Then: Module configuration schema is returned
   - And: Response includes validation rules and defaults

3. **Non-Subscribable Module**
   - Given: Authenticated user with non-subscribable module
   - When: User requests configuration schema
   - Then: 400 error is returned
   - And: Error message indicates module not subscribable

---

## 11. Open Questions / Risks / Decisions

### Open Questions
All open questions have been resolved:
1. Product versioning: Not supported, products are immutable
2. Module versioning: Not supported, modules are immutable
3. Dynamic product creation: Not supported, products are hardcoded
4. Module dependencies: Handled by subscription management

### Risks
1. **Definition Staleness**: Hardcoded definitions may become outdated
2. **Performance**: Large product/module catalogs could impact response times
3. **Consistency**: Manual synchronization between definitions and implementations

### Decisions
1. **Hardcoded Definitions**: Products and modules are defined in code, not database
2. **Read-Only Access**: No write operations for product/module definitions
3. **Immutable Structure**: Product and module definitions cannot be modified at runtime
4. **Centralized Source**: Single source of truth for all product and module information
5. **No Versioning**: Current definitions are always authoritative
6. **Authentication Required**: All access requires valid authentication

---

## 12. Product and Module Definitions

### 12.1 Products

```json
{
  "products": [
    {
      "id": 1,
      "key": "AGENTS_PLATFORM",
      "name": "Agents Platform",
      "description": "AI-powered customer service platform with intelligent agents",
      "availableModuleKeys": ["USER_MANAGEMENT", "TEAM_MANAGEMENT", "ROLE_PERMISSION_MANAGEMENT", "FILES_MANAGEMENT"],
      "targetSegments": ["Customer Service", "Support Teams", "Sales Teams"],
      "useCases": [
        "Automated customer support",
        "Lead qualification",
        "Knowledge base management",
        "Multi-channel communication"
      ],
      "isActive": true
    },
    {
      "id": 2,
      "key": "ONE_INBOX",
      "name": "One Inbox",
      "description": "Unified communication hub for managing all customer interactions",
      "availableModuleKeys": ["USER_MANAGEMENT", "TEAM_MANAGEMENT", "ROLE_PERMISSION_MANAGEMENT", "FILES_MANAGEMENT"],
      "targetSegments": ["Customer Service", "Support Teams", "Sales Teams"],
      "useCases": [
        "Centralized message management",
        "Multi-channel support",
        "Team collaboration",
        "Workflow automation"
      ],
      "isActive": true
    },
    {
      "id": 3,
      "key": "DOCVERSE",
      "name": "DocVerse",
      "description": "Document management and collaboration platform",
      "availableModuleKeys": ["USER_MANAGEMENT", "TEAM_MANAGEMENT", "ROLE_PERMISSION_MANAGEMENT", "FILES_MANAGEMENT"],
      "targetSegments": ["Content Teams", "Knowledge Workers", "Documentation Teams"],
      "useCases": [
        "Document collaboration",
        "Knowledge management",
        "Content creation",
        "Document workflows"
      ],
      "isActive": true
    }
  ]
}
```

### 12.2 Modules

```json
{
  "subscribableModules": [
    {
      "id": 3,
      "key": "USER_MANAGEMENT",
      "code": "UM",
      "name": "User Management",
      "description": "Comprehensive user lifecycle management with organization membership and role assignment",
      "subscribable": true,
      "configurableAttributes": {
        "max_users_per_org": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 10000,
          "default": 10,
          "description": "Maximum number of users allowed per organization"
        },
        "max_orgs_per_user": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 100,
          "default": 5,
          "description": "Maximum number of organizations a user can belong to"
        },
        "user_retention_days": {
          "type": "integer",
          "required": true,
          "min": 30,
          "max": 2555,
          "default": 365,
          "description": "Number of days to retain soft-deleted users"
        }
      },
      "exposedPermissions": [
        "user:create",
        "user:read",
        "user:update",
        "user:delete",
        "user:list",
        "user:deactivate",
        "user:suspend",
        "user:manage_membership",
        "user:view_all"
      ],
      "isActive": true
    },
    {
      "id": 4,
      "key": "TEAM_MANAGEMENT",
      "code": "TM",
      "name": "Team Management",
      "description": "Team creation, member management, and team-based collaboration features",
      "subscribable": true,
      "configurableAttributes": {
        "max_teams": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 1000,
          "default": 5,
          "description": "Maximum number of teams allowed per organization"
        },
        "max_team_members": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 1000,
          "default": 50,
          "description": "Maximum number of members allowed per team"
        },
        "team_retention_days": {
          "type": "integer",
          "required": true,
          "min": 30,
          "max": 365,
          "default": 90,
          "description": "Number of days to retain soft-deleted teams"
        }
      },
      "exposedPermissions": [
        "teams:create",
        "teams:read",
        "teams:update",
        "teams:delete",
        "teams:manage_members",
        "teams:deactivate",
        "teams:list",
        "teams:view_all"
      ],
      "isActive": true
    },
    {
      "id": 5,
      "key": "ROLE_PERMISSION_MANAGEMENT",
      "code": "RPM",
      "name": "Role & Permission Management",
      "description": "Custom role creation, permission assignment, and access control management",
      "subscribable": true,
      "configurableAttributes": {
        "max_custom_roles_per_org": {
          "type": "integer",
          "required": true,
          "min": 5,
          "max": 100,
          "default": 10,
          "description": "Maximum number of custom roles allowed per organization"
        },
        "max_permissions_per_role": {
          "type": "integer",
          "required": true,
          "min": 10,
          "max": 200,
          "default": 50,
          "description": "Maximum number of permissions allowed per role"
        },
        "max_role_assignments_per_user": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 20,
          "default": 5,
          "description": "Maximum number of role assignments allowed per user"
        },
        "role_assignment_audit_retention_days": {
          "type": "integer",
          "required": true,
          "min": 90,
          "max": 2555,
          "default": 365,
          "description": "Number of days to retain role assignment audit logs"
        }
      },
      "exposedPermissions": [
        "roles:create",
        "roles:read",
        "roles:update",
        "roles:delete",
        "roles:assign",
        "roles:admin",
        "permissions:list"
      ],
      "isActive": true
    },
    {
      "id": 6,
      "key": "FILES_MANAGEMENT",
      "code": "FM",
      "name": "Files Management",
      "description": "Secure file storage, organization, and access control with versioning",
      "subscribable": true,
      "configurableAttributes": {
        "max_file_size": {
          "type": "integer",
          "required": true,
          "min": 1048576,
          "max": 104857600,
          "default": 10485760,
          "description": "Maximum file size in bytes (1MB to 100MB)"
        },
        "max_storage_quota": {
          "type": "integer",
          "required": true,
          "min": 1073741824,
          "max": 1099511627776,
          "default": 10737418240,
          "description": "Maximum storage quota in bytes (1GB to 1TB)"
        },
        "max_files_per_user": {
          "type": "integer",
          "required": true,
          "min": 100,
          "max": 10000,
          "default": 1000,
          "description": "Maximum number of files allowed per user"
        },
        "file_retention_days": {
          "type": "integer",
          "required": true,
          "min": 30,
          "max": 365,
          "default": 90,
          "description": "Number of days to retain soft-deleted files"
        },
        "version_history_limit": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 50,
          "default": 10,
          "description": "Maximum number of versions to keep per file"
        }
      },
      "exposedPermissions": [
        "files:upload",
        "files:read",
        "files:update",
        "files:delete",
        "files:admin",
        "files:public:read"
      ],
      "isActive": true
    }
  ],
  "nonSubscribableModules": [
    {
      "id": 0,
      "key": "ACCOUNT_MANAGEMENT",
      "code": "AM",
      "name": "Account Management",
      "description": "Enterprise account lifecycle management and administration",
      "subscribable": false,
      "configurableAttributes": null,
      "exposedPermissions": [
        "account:create",
        "account:read",
        "account:update",
        "account:delete",
        "account:list"
      ],
      "isActive": true
    },
    {
      "id": 1,
      "key": "ORGANIZATION_MANAGEMENT",
      "code": "OM",
      "name": "Organization Management",
      "description": "Organization lifecycle management within enterprise accounts",
      "subscribable": false,
      "configurableAttributes": null,
      "exposedPermissions": [
        "organization:create",
        "organization:read",
        "organization:update",
        "organization:delete",
        "organization:list",
        "organization:assign_owner"
      ],
      "isActive": true
    },
    {
      "id": 2,
      "key": "AUTHENTICATION_AND_AUTHORIZATION",
      "code": "AA",
      "name": "Authentication & Authorization",
      "description": "User authentication, session management, and authorization services",
      "subscribable": false,
      "configurableAttributes": {
        "session_duration_hours": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 24,
          "default": 8,
          "description": "Session duration in hours"
        },
        "max_concurrent_sessions": {
          "type": "integer",
          "required": true,
          "min": 1,
          "max": 10,
          "default": 3,
          "description": "Maximum concurrent sessions per user"
        },
        "rate_limit_login_attempts": {
          "type": "integer",
          "required": true,
          "min": 3,
          "max": 10,
          "default": 5,
          "description": "Maximum login attempts before lockout"
        },
        "rate_limit_window_minutes": {
          "type": "integer",
          "required": true,
          "min": 5,
          "max": 60,
          "default": 15,
          "description": "Rate limit window in minutes"
        }
      },
      "exposedPermissions": [
        "auth:login",
        "auth:logout",
        "auth:refresh",
        "auth:context_switch",
        "auth:password_reset",
        "authz:permission_check",
        "authz:resource_access"
      ],
      "isActive": true
    }
  ]
}
```

---

## Change Log

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0.0 | 2025-01-27 | Initial comprehensive version with product and module definitions | Requirements Team |
