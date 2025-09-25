# Accounts — Core CRUD API (v1)

> **Auth:** Bearer JWT
>
> **Access:** SaaS Administrator **or** Django Staff (`is_staff=true`) only.

Base path: `/api/v1/accounts`

---

### `POST /api/v1/accounts`
*Creates a new account.*

**Request Body**
```json
{
  "name": "Acme Corporation",
  "description": "Enterprise customer account.",
  "contactEmail": "admin@acmecorp.com"
}
```

**Response — 201 Created**
```json
{
  "accountId": "acc_01JABCDEF123",
  "name": "Acme Corporation",
  "description": "Enterprise customer account.",
  "contactEmail": "admin@acmecorp.com",
  "isActive": true,
  "createdBy": "user_9b12",
  "createdAt": "2025-09-24T10:00:00Z",
  "updatedAt": "2025-09-24T10:00:00Z",
  "deletedAt": null
}
```

---

### `GET /api/v1/accounts`
*Retrieves a paginated list of accounts.*

**Response — 200 OK**
```json
{
  "page": 1,
  "pageSize": 25,
  "totalPages": 3,
  "totalItems": 63,
  "items": [
    {
      "accountId": "acc_01JABCDEF123",
      "name": "Acme Corporation",
      "description": "Enterprise customer account.",
      "contactEmail": "admin@acmecorp.com",
      "isActive": true,
      "createdBy": "user_9b12",
      "createdAt": "2025-09-24T10:00:00Z",
      "updatedAt": "2025-09-24T10:00:00Z"
    }
  ]
}
```

---

### `GET /api/v1/accounts/{accountId}`
*Retrieves a single account by ID.*

**Response — 200 OK**
```json
{
  "accountId": "acc_01JABCDEF123",
  "name": "Acme Corporation",
  "description": "Enterprise customer account.",
  "contactEmail": "admin@acmecorp.com",
  "isActive": true,
  "createdBy": "user_9b12",
  "createdAt": "2025-09-24T10:00:00Z",
  "updatedAt": "2025-09-24T10:00:00Z",
  "deletedAt": null
}
```

---

### `PUT /api/v1/accounts/{accountId}`
*Updates an existing account (full or partial fields accepted).*

**Request Body**
```json
{
  "name": "Acme Corp",
  "description": "Updated description.",
  "contactEmail": "owner@acmecorp.com",
  "isActive": false
}
```

**Response — 200 OK**
```json
{
  "accountId": "acc_01JABCDEF123",
  "name": "Acme Corp",
  "description": "Updated description.",
  "contactEmail": "owner@acmecorp.com",
  "isActive": false,
  "createdBy": "user_9b12",
  "createdAt": "2025-09-24T10:00:00Z",
  "updatedAt": "2025-09-24T12:15:32Z",
  "deletedAt": null
}
```

---

### `DELETE /api/v1/accounts/{accountId}`
*Soft-deletes an account.*

**Response — 204 No Content**

---

### Common Error Responses (for all endpoints)

**401 Unauthorized**
```json
{
  "code": "UNAUTHORIZED",
  "message": "Missing or invalid token"
}
```

**403 Forbidden**
```json
{
  "code": "FORBIDDEN",
  "message": "Only SaaS Admin or staff may access this resource"
}
```

**404 Not Found**
```json
{
  "code": "ACCOUNT_NOT_FOUND",
  "message": "Account does not exist"
}
```

**409 Conflict** (create/update)
```json
{
  "code": "ACCOUNT_NAME_EXISTS",
  "message": "Account name already exists"
}
```