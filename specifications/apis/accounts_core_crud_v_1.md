# Accounts — Core CRUD API (v1) — Implementation

> **Auth:** Bearer JWT  
> **Access:** SaaS Administrator **or** Django Staff (`is_staff=true`) only  
> **Notes:** Snake_case field names everywhere; simple CRUD only (no custom activate/deactivate/restore endpoints). `DELETE` performs **soft delete**.

Base path: `/api/v1/accounts`

---

## Create Account
### `POST /api/v1/accounts`
Creates a new account.

**Request Body**
```json
{
  "name": "Acme Corporation",
  "description": "Enterprise customer account.",
  "contact_email": "admin@acmecorp.com"
}
```

**Response — 201 Created**
```json
{
  "id": "3f7e8d7e-8b1a-4f1a-8e3d-0a3b9f5b1b8a",
  "name": "Acme Corporation",
  "description": "Enterprise customer account.",
  "contact_email": "admin@acmecorp.com",
  "is_active": true,
  "created_by": "user_uuid",
  "updated_by": "user_uuid",
  "created_at": "2025-09-24T10:00:00Z",
  "updated_at": "2025-09-24T10:00:00Z",
  "deleted_at": null
}
```

**Errors**
- `400 Bad Request` – validation (e.g., invalid email, name length, uniqueness)
- `401 Unauthorized` – missing/invalid token
- `403 Forbidden` – not SaaS Admin or staff

---

## List Accounts
### `GET /api/v1/accounts`
Retrieves a paginated list of accounts (soft-deleted records are excluded).

**Response — 200 OK** (DRF default pagination)
```json
{
  "count": 63,
  "next": "https://api.example.com/api/v1/accounts/?page=2",
  "previous": null,
  "results": [
    {
      "id": "3f7e8d7e-8b1a-4f1a-8e3d-0a3b9f5b1b8a",
      "name": "Acme Corporation",
      "description": "Enterprise customer account.",
      "contact_email": "admin@acmecorp.com",
      "is_active": true,
      "created_by": "user_uuid",
      "updated_by": "user_uuid",
      "created_at": "2025-09-24T10:00:00Z",
      "updated_at": "2025-09-24T10:00:00Z",
      "deleted_at": null
    }
  ]
}
```

**Errors**
- `401 Unauthorized`
- `403 Forbidden`

---

## Get Account by ID
### `GET /api/v1/accounts/{id}`
Retrieves a single account by UUID.

**Response — 200 OK**
```json
{
  "id": "3f7e8d7e-8b1a-4f1a-8e3d-0a3b9f5b1b8a",
  "name": "Acme Corporation",
  "description": "Enterprise customer account.",
  "contact_email": "admin@acmecorp.com",
  "is_active": true,
  "created_by": "user_uuid",
  "updated_by": "user_uuid",
  "created_at": "2025-09-24T10:00:00Z",
  "updated_at": "2025-09-24T10:00:00Z",
  "deleted_at": null
}
```

**Errors**
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`

---

## Update Account (full)
### `PUT /api/v1/accounts/{id}`
Updates an existing account. You may also toggle `is_active` here.

**Request Body**
```json
{
  "name": "Acme Corp",
  "description": "Updated description.",
  "contact_email": "owner@acmecorp.com",
  "is_active": false
}
```

**Response — 200 OK**
```json
{
  "id": "3f7e8d7e-8b1a-4f1a-8e3d-0a3b9f5b1b8a",
  "name": "Acme Corp",
  "description": "Updated description.",
  "contact_email": "owner@acmecorp.com",
  "is_active": false,
  "created_by": "user_uuid",
  "updated_by": "user_uuid",
  "created_at": "2025-09-24T10:00:00Z",
  "updated_at": "2025-09-24T12:15:32Z",
  "deleted_at": null
}
```

**Errors**
- `400 Bad Request` – validation (incl. uniqueness)
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`

---

## Update Account (partial)
### `PATCH /api/v1/accounts/{id}`
Partially updates an account. Example toggling active state only:

**Request Body**
```json
{
  "is_active": true
}
```

**Response — 200 OK**
```json
{
  "id": "3f7e8d7e-8b1a-4f1a-8e3d-0a3b9f5b1b8a",
  "name": "Acme Corp",
  "description": "Updated description.",
  "contact_email": "owner@acmecorp.com",
  "is_active": true,
  "created_by": "user_uuid",
  "updated_by": "user_uuid",
  "created_at": "2025-09-24T10:00:00Z",
  "updated_at": "2025-09-24T12:20:05Z",
  "deleted_at": null
}
```

**Errors**
- `400 Bad Request`
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`

---

## Delete Account (soft)
### `DELETE /api/v1/accounts/{id}`
Soft-deletes an account. Soft-deleted records are excluded from default lists and lookups.

**Response — 204 No Content**

**Errors**
- `401 Unauthorized`
- `403 Forbidden`
- `404 Not Found`

---

## Common Validation Rules
- `name`: 1–100 chars; **case-insensitive unique**.
- `description`: ≤ 500 chars (optional).
- `contact_email`: valid email; unique.

---

