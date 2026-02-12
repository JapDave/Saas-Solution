# Acceptance Tests

This directory contains end-to-end acceptance tests that verify the actual API endpoints work correctly.

## Overview

Acceptance tests make real HTTP requests to the API and test the full request/response cycle, verifying authentication, authorization, and business logic together.

## Running Acceptance Tests

### Step-by-Step Guide

#### 1. Stop running Docker containers (optional - removes volumes)

```bash
docker-compose -f .\docker\compose.yaml down -v
```

#### 2. Pull latest changes (optional)

```bash
git pull
```

#### 3. Start all services in background

```bash
docker-compose -f .\docker\compose.yaml up --force-recreate -d
```

#### 4. Run tests

**Run all acceptance tests:**
```bash
docker compose -f docker/compose.yaml run --rm -e API_BASE_URL=https://nginx:8443/api -e VERIFY_SSL=false web pytest acceptance_tests/ -v -m acceptance
```

**Run a specific test file:**
```bash
docker compose -f docker/compose.yaml run --rm -e API_BASE_URL=https://nginx:8443/api -e VERIFY_SSL=false web pytest acceptance_tests/<test_file_name>.py -v -m acceptance
```

**Run a specific test class:**
```bash
docker compose -f docker/compose.yaml run --rm -e API_BASE_URL=https://nginx:8443/api -e VERIFY_SSL=false web pytest acceptance_tests/<test_file_name>.py::<class_name> -v -m acceptance
```

**Run a specific test:**
```bash
docker compose -f docker/compose.yaml run --rm -e API_BASE_URL=https://nginx:8443/api -e VERIFY_SSL=false web pytest acceptance_tests/<test_file_name>.py::<class_name>::<test_name> -v -m acceptance
```

## Test Structure

- `conftest.py` - Shared fixtures for HTTP clients and authentication
- `test_*.py` - Test files organized by API resource/feature

## Test Data Management

Tests automatically truncate database tables before each test to ensure clean state. The `truncate_test_data` fixture (autouse=True) runs automatically and:

- **Preserves the superuser** (identified by `ADMIN_EMAIL` or `is_superuser=True`)
- **Truncates test data** in the correct order to respect foreign key constraints:
  1. DataChangeLog
  2. AuditLog
  3. UserOrganization
  4. Organization
  5. Account
  6. User (except superuser)
