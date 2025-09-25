# Accounts — Core CRUD Test Suite (v1)

> **Scope**: Core CRUD endpoints only
> - `POST /api/v1/accounts`
> - `GET /api/v1/accounts`
> - `GET /api/v1/accounts/{accountId}`
> - `PUT /api/v1/accounts/{accountId}` (accepts full/partial updates per API spec)
> - `DELETE /api/v1/accounts/{accountId}` (soft delete)
>
> **Auth**: Bearer JWT **required**
> **Access**: **SaaS Admin** or **Django Staff** (`is_staff=true`) only. Others → 403
>
> **Note**: Document lists **test cases (happy + edge)** only; no code.

---

## 0) Fixtures & Setup
- **Actors**:
  - `saas_admin` (JWT token)
  - `staff_user` (is_staff=true, JWT token)
  - `regular_user` (non-staff, JWT token)
  - `unauthenticated` (no token)
- **Reusable data**:
  - Valid account body `A0`:
    ```json
    {"name":"Acme Corporation","description":"Enterprise customer account.","contactEmail":"admin@acmecorp.com"}
    ```
  - Existing account `ACC1` created by `saas_admin` for read/update/delete scenarios
- **Conventions**:
  - Include header `X-Request-ID` in all write tests; assert echoed/logged if system supports it
  - Use unique names/emails per test unless testing conflicts

---

## A) Create Account — `POST /api/v1/accounts`

### A1 Happy paths
1. **SaaS Admin creates minimal**  
   **Req**: `{name, contactEmail}` (no description)  
   **Expect**: `201`, body contains `accountId`, canonicalized fields
2. **Staff creates full**  
   **Req**: `A0`  
   **Expect**: `201`, body matches input, `createdBy=staff_user`
3. **Idempotent retry**  
   **Req**: same payload + same `Idempotency-Key` repeated  
   **Expect**: second call returns same `201` (or `200`) with same `accountId`; **no duplicate row**

### A2 Validation edges
4. **Empty name** → `400`
5. **Name length = 1** (boundary) → `201`
6. **Name length > 100** → `400`
7. **Name with leading/trailing spaces** → `201` with trimmed (if trimming) or `400` (if strict); assert chosen behavior
8. **Unicode name** (e.g., `“Åcme 株式会社”`) → `201`
9. **Bad email format** (`contactEmail="not-an-email"`) → `400`
10. **Very long email (near RFC limits)** → if within system limit → `201`, else `400` (document limit)

### A3 Uniqueness & case rules
11. **Duplicate name (same case)** → `409 ACCOUNT_NAME_EXISTS`
12. **Duplicate name (different case)** → `409` (case-insensitive uniqueness)
13. **Duplicate contactEmail** → `409 ACCOUNT_EMAIL_EXISTS`

### A4 AuthZ & AuthN
14. **Regular user** → `403`
15. **Unauthenticated** → `401`

### A5 Security & misc
16. **Missing/invalid `Content-Type`** → `415` or `400` (documented behavior)
17. **Unexpected fields** in payload → `400` (strict) or ignore (lenient); assert chosen behavior
18. **Large description (exactly 500 chars)** → `201`; **501 chars** → `400`
19. **XSS in description/name** (`<script>…</script>`) → either sanitized in response or `400`; assert no raw execution/echo

---

## B) List Accounts — `GET /api/v1/accounts`

### B1 Happy paths
1. **SaaS Admin default pagination**  
   **Expect**: `200`, `page=1`, `pageSize=25` (or `page_size`), non-empty `items`, total counters
2. **Staff with empty dataset**  
   **Setup**: clear/isolated DB  
   **Expect**: `200`, `items=[]`, `totalItems=0`

### B2 Filters & query params
3. **Filter is_active=true** → all returned have `is_active=True`
4. **Search `q=acme`** → items contain `name` or `contactEmail` like `acme` (case-insensitive)
5. **Pagination boundary**: request `pageSize=1` then `page=2` returns next item
6. **Max pageSize boundary (200)** → `200`; **201** → `400`
7. **Invalid page (`-1`) / pageSize (`0`)** → `400`
8. **Request beyond last page** → `200` with empty `items`

### B3 AuthZ & AuthN
9. **Regular user** → `403`
10. **Unauthenticated** → `401`

### B4 Performance & N+1 (non-functional)
11. **Seed 1k accounts** → P95 under budget (e.g., <200ms)  
12. **Query count** → No N+1 vs creators/metadata (if included)

---

## C) Get Account — `GET /api/v1/accounts/{accountId}`

### C1 Happy paths
1. **SaaS Admin gets existing** → `200` full resource
2. **Staff gets existing** → `200`

### C2 Edge IDs & states
3. **Non-existent ID** → `404 ACCOUNT_NOT_FOUND`
4. **Soft-deleted ID** → `404`
5. **Malformed ID** (wrong format/length) → `400` or `404` per routing; assert chosen behavior

### C3 AuthZ & AuthN
6. **Regular user** → `403`
7. **Unauthenticated** → `401`

---

## D) Update Account — `PUT /api/v1/accounts/{accountId}`
> Spec allows full or partial updates via PUT. If system enforces full-replacement semantics, adjust expected errors for missing required fields.

### D1 Happy paths
1. **SaaS Admin updates name + email** → `200`, fields updated, `updatedAt` changed
2. **Staff partial update (only description)** → `200`, other fields unchanged
3. **Idempotent retry** (same body + same `Idempotency-Key`) → `200`, no extra audit entry

### D2 Conflicts & validation
4. **Change name to existing name (same case)** → `409 ACCOUNT_NAME_EXISTS`
5. **Change name to existing name (different case)** → `409`
6. **Change contactEmail to existing** → `409 ACCOUNT_EMAIL_EXISTS`
7. **Set name to empty** → `400`
8. **Name exactly 100 chars** → `200`; **101** → `400`
9. **Email invalid** → `400`
10. **Description 500 chars** → `200`; **501** → `400`
11. **Whitespace-only name** → `400`
12. **Unicode round-trip** (update to unicode name) → `200`, value preserved

### D3 Concurrency & versioning (if ETag/If-Match used)
13. **Concurrent updates without ETag** → last write wins; `updatedAt` reflects final write
14. **With ETag** (if supported): stale `If-Match` → `412 Precondition Failed`

### D4 AuthZ & AuthN
15. **Regular user** → `403`
16. **Unauthenticated** → `401`

---

## E) Delete Account — `DELETE /api/v1/accounts/{accountId}`
> Soft delete; resource becomes non-readable. (Deactivation rules and subscription checks are part of lifecycle spec; for **Core CRUD** cover soft-delete behavior.)

### E1 Happy paths
1. **SaaS Admin delete existing** → `204` (or `200` minimal body), subsequent GET → `404`
2. **Staff delete existing** → expected same outcome if allowed in policy; if only Admin may delete, expect `403` for staff (choose and assert policy)

### E2 Edges & safety
3. **Delete already deleted** → `404` (or `204` idempotent); assert chosen behavior
4. **Delete non-existent** → `404`
5. **Delete with dependent child resources (orgs exist)** → `400` or `409` (if business rules require preconditions); assert message/codes
6. **Delete with active subscriptions** → `400 ACCOUNT_HAS_ACTIVE_SUBSCRIPTIONS` (if enforced at CRUD layer)

### E3 AuthZ & AuthN
7. **Regular user** → `403`
8. **Unauthenticated** → `401`

---

## F) Common Security & Robustness
1. **Auth header variations**: missing `Bearer`, extra spaces, lowercase `bearer` → `401` (or accept canonicalization); assert chosen behavior
2. **Unsupported media type** on POST/PUT → `415`
3. **Unexpected JSON types** (e.g., `name: 123`) → `400`
4. **Duplicate keys in JSON** → last-one-wins or `400` depending on parser; assert chosen behavior
5. **Very large payload** (over global request size) → `413 Payload Too Large`
6. **SQL/NoSQL injection strings in inputs** → `400`; assert no error leakage
7. **HTML/script in fields** → stored as plain text or rejected; assert no XSS reflection
8. **Rate limit**: exceed write endpoints → `429` with retry headers (if enabled)

---

## G) Observability & Audit (if implemented)
1. **Audit on create/update/delete**: verify entries with actor, before/after, `requestId`
2. **Request ID propagation**: server logs contain the `X-Request-ID` value
3. **Error logging**: 4xx validation → warn/info, 5xx → error; no sensitive data in logs

---

## H) Data Integrity & Consistency
1. **Case-insensitive uniqueness** persists across create→update sequences
2. **Soft delete**: subsequent create with the same name/email is **allowed or blocked** per policy—assert chosen behavior (e.g., allow re-use after delete)
3. **Timestamps**: `createdAt` immutable; `updatedAt` monotonic increasing
4. **Serialization**: field order stable (optional), date format ISO-8601 with `Z`

---

## I) Role/Access Matrix (quick reference)
| Endpoint | SaaS Admin | Staff | Regular user | Unauth |
|---|---|---|---|---|
| POST /accounts | ✅ | ✅ | ❌ (403) | ❌ (401) |
| GET /accounts | ✅ | ✅ | ❌ (403) | ❌ (401) |
| GET /accounts/{id} | ✅ | ✅ | ❌ (403) | ❌ (401) |
| PUT /accounts/{id} | ✅ | ✅ | ❌ (403) | ❌ (401) |
| DELETE /accounts/{id} | ✅ | ⚠️ *policy* | ❌ (403) | ❌ (401) |

> If deletion must be **Admin-only**, mark Staff as ❌ and ensure tests expect `403`.

---

## J) Idempotency & Retries
1. **POST with Idempotency-Key**: same key + same body → single resource
2. **PUT with Idempotency-Key**: same key + same body → no-op second call (200)
3. **Different body, same key** → `409/422` per policy; assert behavior

---

## K) Backward Compatibility (when schema evolves)
1. **Unknown fields tolerated on input** (soft compatibility) or rejected (strict) → assert policy
2. **Response contains only documented fields** — no accidental leakage of internal fields

---

## L) Smoke Checklist per Endpoint
- Status code correct
- JSON schema matches spec (types, requireds)
- Business rules enforced (uniqueness, length, email)
- AuthZ enforced (role matrix)
- Side-effects: timestamps/audit updated, search index (if any) updated
- Logs contain correlation ID

