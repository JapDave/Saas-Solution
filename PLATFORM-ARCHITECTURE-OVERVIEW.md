# Platform Architecture Overview

> **Concise overview of the Hudhud Systems platform architecture and core module organization**

---

## Executive Summary

The Hudhud Systems platform is a comprehensive SaaS solution built on a modular architecture that supports multiple products (Agents Platform, One Inbox, and DocVerse) through a shared set of core modules. The platform provides enterprise-grade account management, multi-tenant organization support, and subscription-based feature access control.

---

## Platform Architecture

### Core Design Principles

1. **Multi-Tenant Architecture**: Complete data isolation between accounts and organizations
2. **Subscription-Based Access**: Features are gated by module subscriptions with configurable limits
3. **Role-Based Security**: Granular permission system with custom role creation
4. **Modular Design**: Core modules provide foundational services to all products
5. **Enterprise-Ready**: Supports enterprise accounts with multiple organizations

### Organization-Module Relationship Through Subscriptions

```
Organization
├── Core Modules (Always Available)
│   ├── Account Management
│   ├── Organization Management
│   └── Authentication & Authorization
└── Subscribable Modules (Subscription Required)
    ├── User Management ← Subscription Controls: max_users_per_org, max_orgs_per_user
    ├── Teams Management ← Subscription Controls: max_teams, max_team_members
    ├── Role & Permission Management ← Subscription Controls: max_custom_roles_per_org
    └── Files Management ← Subscription Controls: max_storage_quota, max_file_size

Subscription Model:
- Organizations subscribe to individual modules
- Each subscription has configurable attributes (limits, quotas)
- Permissions are filtered based on active subscriptions
- Real-time enforcement of subscription limits
```

---

## Core Modules Architecture

### 1. Foundation Layer

#### **Account Management**
- **Purpose**: Top-level enterprise customer account management
- **Scope**: Account lifecycle, multi-organization support, enterprise administration
- **Key Features**: Account CRUD, lifecycle management, data isolation

#### **Organization Management**
- **Purpose**: Business unit management within enterprise accounts
- **Scope**: Organization CRUD, ownership assignment, tenant isolation
- **Key Features**: Organization lifecycle, ownership transfer, complete data isolation

### 2. Identity & Access Layer

#### **Authentication & Authorization**
- **Purpose**: Secure user authentication and comprehensive authorization
- **Scope**: User login, session management, permission resolution, subscription-based access
- **Key Features**: Multi-organization sessions, context switching, permission caching
- **Security**: JWT tokens, bcrypt password hashing, rate limiting

#### **User Management**
- **Purpose**: User lifecycle management across multiple organizations
- **Scope**: User CRUD, multi-organization membership, role assignment
- **Key Features**: Cross-organization membership, user status management, session context

#### **Role & Permission Management**
- **Purpose**: Comprehensive role and permission system with subscription filtering
- **Scope**: Custom role creation, permission assignment, authorization logic
- **Key Features**: System roles, custom roles, predefined roles, subscription-based permissions
- **Flexibility**: Supports custom roles per organization

### 3. Collaboration Layer

#### **Teams Management**
- **Purpose**: Team-based collaboration within organizations
- **Scope**: Team CRUD, member management, shared resources
- **Key Features**: Team creation, member assignment, team-based permissions

### 4. Content & Storage Layer

#### **Files Management**
- **Purpose**: Secure file storage and management across the platform
- **Scope**: File upload, versioning, access control, metadata management
- **Key Features**: File versioning, access control, quota management, integrity verification

### 5. Business Logic Layer

#### **Subscription Management**
- **Purpose**: Module subscription management with configurable attributes
- **Scope**: Subscription lifecycle, usage tracking, configuration validation
- **Key Features**: Real-time usage enforcement, configurable limits, subscription status management
- **Flexibility**: Supports trial, active, suspended, expired, and cancelled states

#### **Products & Modules Management**
- **Purpose**: Centralized definition of all products and modules
- **Scope**: Product definitions, module specifications, configuration schemas
- **Key Features**: Product discovery, module configuration, subscription validation
- **Products**: 3 defined products with 6 subscribable modules

---

## Module Dependencies

### Dependency Graph

```
Products & Modules Management
    ↑
Subscription Management
    ↑
┌─── Authentication & Authorization ───┐
│                                      │
├─── User Management ──────────────────┤
│                                      │
├─── Role & Permission Management ─────┤
│                                      │
├─── Teams Management ─────────────────┤
│                                      │
└─── Files Management ─────────────────┘
    ↑
Account Management
    ↑
Organization Management
```

### Key Dependencies

1. **Authentication & Authorization** is foundational - all modules depend on it
2. **User Management** depends on Account and Organization Management
3. **Role & Permission Management** depends on User and Subscription Management
4. **Teams Management** depends on Organization, User, and Role Management
5. **Files Management** depends on all identity and access modules
6. **Subscription Management** depends on Products & Modules Management

---

## Product Integration

### Current Products

1. **Agents Platform**: AI-powered customer service with intelligent agents
2. **One Inbox**: Unified communication hub for customer interactions
3. **DocVerse**: Document management and collaboration platform

### Module Distribution

All products share the same core modules:
- **User Management**: Multi-organization user lifecycle
- **Team Management**: Collaborative team structures
- **Role & Permission Management**: Custom access control
- **Files Management**: Secure file storage and sharing

### Subscription Model

- **Core Modules**: Always available (Account, Organization, Authentication)
- **Subscribable Modules**: Gated by subscription (User, Teams, Roles, Files)
- **Configurable Attributes**: Per-module limits and quotas
- **Usage Tracking**: Real-time enforcement of subscription limits

---

## Security Architecture

### Multi-Layer Security

1. **Authentication Layer**: JWT tokens, session management, MFA support
2. **Authorization Layer**: Role-based access control, permission resolution
3. **Data Isolation**: Complete tenant separation at account and organization levels
4. **Audit Trail**: Comprehensive logging of all operations
5. **Rate Limiting**: Protection against abuse and DoS attacks

### Permission System

- **System Roles**: Platform-level roles (SaaS Administrator, Account Manager)
- **User Roles**: Account and Organization ownership roles
- **Custom Roles**: Organization-defined roles with specific permissions
- **Subscription Filtering**: Permissions only available for subscribed modules

---

## Roles & Permissions Hierarchy

### Role Types and Hierarchy

The platform implements a multi-layered role system with clear hierarchy and scope:

#### 1. System Roles (Platform Level)
**Scope**: Entire platform
**Assignment**: Restricted to @hudhud.ai email addresses
**Immutable**: Cannot be modified, deleted, or have permissions changed

- **SaaS Administrator**
  - Full platform access
  - Can manage all accounts, organizations, and users
  - Can create and modify all subscriptions
  - Can access all system functions

- **SaaS Account Manager**
  - Can manage assigned accounts and their organizations
  - Can create subscriptions for assigned accounts
  - Read-only access to assigned accounts

#### 2. User Roles (Account/Organization Level)
**Scope**: Account or Organization level
**Assignment**: Can be assigned to any user in the organization
**Immutable**: Cannot be modified, deleted, or have permissions changed

- **Account Owner**
  - Full access to account and all its organizations
  - Can create organizations within the account
  - Can assign organization owners
  - Can manage account-level settings

- **Account Administrator**
  - Administrative access to account organizations
  - Can manage users across account organizations
  - Cannot transfer account ownership

- **Organization Owner**
  - Full access to specific organization
  - Can manage all organization resources
  - Can assign organization administrators
  - Can transfer organization ownership

- **Organization Administrator**
  - Administrative access to specific organization
  - Can manage organization users and teams
  - Cannot transfer organization ownership

#### 3. Custom Roles (Organization Level)
**Scope**: Organization level
**Assignment**: Can be assigned to organization members
**Mutable**: Can be created, modified, and deleted by organization administrators

##### Predefined Custom Roles
Automatically created when organization subscribes to modules:

- **Team Manager**: Manage organization teams
- **Team Viewer**: View organization teams
- **Team Admin**: Full team management
- **File Manager**: Manage organization files
- **File Viewer**: View organization files
- **File Contributor**: Upload and manage team files
- **User Manager**: Manage organization users
- **User Viewer**: View organization users
- **User Admin**: Full user management
- **Security Admin**: Manage authentication settings
- **Session Manager**: Manage user sessions

##### User-Defined Custom Roles
Created manually by organization administrators:
- Fully customizable permissions (within subscription limits)
- Can be modified, deleted, and renamed
- Subject to organization's subscription limits

### Permission Hierarchy Model

```
Permission Resolution Flow:
1. User Authentication → Valid Session
2. Organization Context → Current Organization
3. Active Roles → User's roles in current organization
4. Subscription Filtering → Available permissions from subscribed modules
5. Permission Intersection → Final effective permissions

Permission Types:
├── Platform Permissions (System roles only)
├── Account Permissions (Account-level roles)
├── Organization Permissions (Organization-level roles)
└── Module Permissions (Filtered by subscription)
    ├── User Management Permissions
    ├── Teams Management Permissions
    ├── Role & Permission Management Permissions
    └── Files Management Permissions
```

### Permission Enforcement

#### 1. Subscription-Based Filtering
- Users only have permissions for modules their organization has subscribed to
- Permission availability is checked in real-time
- Subscription changes immediately affect user permissions

#### 2. Role-Based Access Control (RBAC)
- Permissions are granted through roles, not directly to users
- Users can have multiple roles within an organization
- Role permissions are additive (user gets all permissions from all their roles)

#### 3. Scope-Based Access Control
- **Platform Scope**: System roles only
- **Account Scope**: Account-level roles and permissions
- **Organization Scope**: Organization-level roles and permissions
- **Team Scope**: Team-based permissions (inherited from organization)
- **Resource Scope**: Individual resource ownership and permissions

#### 4. Permission Inheritance
```
Account Owner
├── Inherits: All Account permissions
└── Inherits: All Organization permissions (for all orgs in account)

Organization Owner
├── Inherits: All Organization permissions
└── Inherits: All Team permissions (for all teams in organization)

Team Manager
├── Inherits: Team management permissions
└── Inherits: Team member permissions
```

### Permission Examples

#### Example 1: User with Multiple Roles
```
User: john.doe@company.com
Organization: Marketing Department
Roles: Organization Admin + Team Manager + File Manager

Effective Permissions:
├── Organization Admin permissions (full org access)
├── Team Manager permissions (team management)
├── File Manager permissions (file management)
└── All permissions filtered by active subscriptions
```

#### Example 2: Permission Resolution Process
```
1. User requests to create a team
2. System checks: User has "teams:create" permission?
3. System checks: Organization has Teams Management subscription?
4. System checks: Organization hasn't exceeded team limits?
5. If all checks pass: Allow team creation
6. If any check fails: Deny with specific error message
```

### Security Features

#### 1. Permission Caching
- Permission results cached for 5 minutes
- Cache invalidated on role changes or subscription changes
- Reduces permission check latency

#### 2. Audit Logging
- All permission checks logged
- Role assignments and removals logged
- Permission changes tracked with before/after values

#### 3. Rate Limiting
- Permission check rate limiting per user
- Role assignment rate limiting per organization
- Protection against permission enumeration attacks

---

## Data Architecture

### Data Isolation

- **Account Level**: Complete isolation between enterprise accounts
- **Organization Level**: Complete isolation between organizations within accounts
- **User Level**: Multi-organization membership with proper access control
- **Team Level**: Team-based resource sharing within organizations

### Data Retention

- **Soft Delete**: All entities support soft deletion for compliance
- **Retention Periods**: 7 years for accounts/organizations, 30-365 days for other entities
- **Audit Logs**: 1 year retention for security and compliance
- **File Storage**: 30 days retention for deleted files

---

## Integration Points

### External Systems

- **Billing System**: Subscription management integration
- **Email Service**: User notifications and password reset
- **Storage Service**: File storage and retrieval
- **Analytics**: Usage tracking and telemetry

### API Design

- **RESTful APIs**: Standard HTTP methods and status codes
- **Authentication**: JWT token-based authentication
- **Rate Limiting**: Per-user and per-organization limits
- **Error Handling**: Comprehensive error messages and retry logic

---

## Future Considerations

### Extensibility

- **New Products**: Easy addition of new products using existing modules
- **New Modules**: Framework for adding new subscribable modules
- **Custom Attributes**: Configurable subscription attributes per module
- **Role Templates**: Predefined role templates for common use cases

### Scalability

- **Horizontal Scaling**: Stateless design supports horizontal scaling
- **Database Sharding**: Account-based sharding for large scale
- **Caching**: Redis-based caching for performance optimization
- **CDN Integration**: File delivery optimization

---

## Conclusion

The Hudhud Systems platform provides a robust, scalable, and secure foundation for enterprise SaaS applications. The modular architecture ensures that core functionality is shared across all products while maintaining complete data isolation and flexible subscription-based access control. The platform is designed to scale from small teams to large enterprises with multiple users and organizations.

---

*Last Updated: 2025-01-27*
*Version: 1.0.0*