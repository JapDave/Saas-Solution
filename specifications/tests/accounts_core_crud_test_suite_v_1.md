# Accounts — Core CRUD Test Suite (v1) — Updated to Current Implementation

> **Scope**: Core CRUD endpoints only (no custom lifecycle endpoints)  
> **Auth**: Bearer JWT **required**  
> **Access**: **SaaS Admin** or **Django Staff** only  
> **Pagination**: DRF default — `count`, `next`, `previous`, `results`

Endpoints:
- `POST /api/v1/accounts`
- `GET /api/v1/accounts`
- `GET /api/v1/accounts/{id}`
- `PUT /api/v1/accounts/{id}`
- `PATCH /api/v1/accounts/{id}`
- `DELETE /api/v1/accounts/{id}`

---

## 0) Fixtures & Setup
- Actors: `saas_admin`, `staff_user`, `regular_user`, `unauthenticated`
- Reusable body `A0`:
```json
{"name":"Acme Corporation","description":"Enterprise customer account.","contact_email":"admin@acmecorp.com"}
```
- Pre-create `ACC1` for read/update/delete scenarios

---

## A) Create — `POST /api/v1/accounts`
### Happy paths
1. Admin minimal (name + contact_email) → `201` with full resource
2. Staff full body (`A0`) → `201`, `created_by`/`updated_by` set to staff

### Validation edges
3. Empty name → `400`
4. Name length = 1 → `201`; length = 101 → `400`
5. Invalid `contact_email` → `400`
6. Unicode name → `201`
7. Duplicate `name` (same/different case) → `400` (unique constraint)
8. Duplicate `contact_email` → `400`
9. Description exactly 500 → `201`; 501 → `400`

### Auth
10. Regular user → `403`; unauthenticated → `401`

---

## B) List — `GET /api/v1/accounts`
### Happy paths
1. Default page → `200`, contains `count`, `next`, `previous`, `results`
2. Empty dataset → `200`, `count=0`, `results=[]`

### Pagination edges
3. `page_size=1` then `page=2` (if enabled in settings) → `200`, next item returned
4. Invalid `page` (`-1`) / `page_size` (`0`) → `400` (if validated)
5. Beyond last page → `200`, `results=[]`

### Auth
6. Regular user → `403`; unauthenticated → `401`

---

## C) Retrieve — `GET /api/v1/accounts/{id}`
1. Admin gets existing → `200`
2. Staff gets existing → `200`
3. Non-existent UUID → `404`
4. Soft-deleted UUID → `404`
5. Malformed UUID → `404` (or `400`) per routing
6. Auth: regular → `403`, unauth → `401`

---

## D) Update — `PUT /api/v1/accounts/{id}`
### Happy paths
1. Admin updates `name` + `contact_email` → `200`, `updated_at` changes
2. Staff updates only `description` → `200`, other fields unchanged
3. Toggle `is_active` to `false` → `200`, verify persisted

### Validation/conflicts
4. Set `name` empty → `400`
5. `name` 100 chars → `200`; 101 → `400`
6. `contact_email` invalid → `400`
7. Change `name` to duplicate (case-insensitive) → `400`
8. Change `contact_email` to duplicate → `400`

### Auth
9. Regular user → `403`; unauth → `401`

---

## E) Partial Update — `PATCH /api/v1/accounts/{id}`
1. Toggle only `is_active` → `200`
2. Update only `description` → `200`
3. Invalid type (e.g., `name: 123`) → `400`
4. Auth: regular → `403`; unauth → `401`

---

## F) Delete (soft) — `DELETE /api/v1/accounts/{id}`
1. Admin delete existing → `204`; subsequent GET → `404`
2. Staff delete existing → `204` (if policy allows; else expect `403` per project policy)
3. Delete already deleted → `404` (or `204` idempotent; choose and assert)
4. Delete non-existent → `404`

---

## G) Security & Robustness
1. Auth header variants (missing `Bearer`, casing) → `401`
2. Unsupported media type on POST/PUT/PATCH → `415`
3. Oversized payload → `413`
4. Injection/XSS strings in inputs → no execution/echo, sanitized or `400`

---

## H) Data Integrity
1. Case-insensitive uniqueness holds across create→update
2. Timestamps: `created_at` immutable; `updated_at` monotonic
3. Soft delete: deleted items never appear in default list/get

---

## I) Role/Access Matrix
| Endpoint | SaaS Admin | Staff | Regular | Unauth |
|---|---|---|---|---|
| POST /accounts | ✅ | ✅ | ❌ 403 | ❌ 401 |
| GET /accounts | ✅ | ✅ | ❌ 403 | ❌ 401 |
| GET /accounts/{id} | ✅ | ✅ | ❌ 403 | ❌ 401 |
| PUT /accounts/{id} | ✅ | ✅ | ❌ 403 | ❌ 401 |
| PATCH /accounts/{id} | ✅ | ✅ | ❌ 403 | ❌ 401 |
| DELETE /accounts/{id} | ✅ | ✅* | ❌ 403 | ❌ 401 |

`*` If deletion must be Admin-only in your policy, mark Staff as ❌ 403 and test accordingly.

