# Modular SaaS backend

A Django REST backend for account and organization management, teams, roles, subscriptions and configurable agent workflows. This repository shows how a larger business API is organized into domain modules with shared services, permissions and test fixtures.

## What to inspect

| Area | Source |
| --- | --- |
| Tenant and account boundaries | `apps/accounts`, `apps/organizations`, `apps/teams` |
| Authentication and permissions | `apps/authentication`, `apps/users`, `apps/roles` |
| Product access and subscriptions | `apps/products`, `apps/subscriptions` |
| Agent, flow and integration configuration | `apps/agents`, `apps/flows`, `apps/integrations`, `apps/llms`, `apps/tools` |
| Shared errors, middleware and tests | `apps/common` |

Stack: Python, Django REST Framework, PostgreSQL, Redis, Docker and OpenAPI. Optional storage and observability integrations require their own configuration. Agent configuration APIs do not by themselves demonstrate a complete hosted inference system.

## Local demo

Use Docker Compose. The demo binds the API to localhost and uses development settings.

```bash
cp .env.example .env
docker compose -f docker/compose.demo.yaml up --build
```

Open http://localhost:8000/api/docs/ for Swagger, or http://localhost:8000/api/redoc/ for ReDoc. Create an administrator interactively:

```bash
docker compose -f docker/compose.demo.yaml exec web python manage.py createsuperuser
```

The entrypoint runs migrations, initializes roles and LLM records, and collects static files. The original `docker/docker-compose.yml` remains available for the Nginx/TLS layout; it requires separate certificate configuration.

## Local tests

With Python 3.12 in a virtual environment:

```bash
pip install -r requirements.txt
pytest apps --ds=config.settings.test
```

The test settings use PostgreSQL, an in-memory cache and local email. Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` and `DB_PORT` for a local database with test-database creation privileges. PostgreSQL is required by the existing SQL migrations. Real external services require separate integration testing. Network acceptance tests have a separate configuration in `pytest-acceptance.ini`.

## Deployment scope

This is a backend portfolio/reference codebase. Before deployment, review dependency support, tenant authorization, CORS, secrets, database migrations, backups and provider integrations for the target environment. Never deploy the development settings or example secrets. `.env` is intentionally excluded; provision secrets outside source control.

See the existing environment and observability documents for the broader configuration options.

A GitHub Actions compile/system-check template is provided in `docs/ci/checks.yml`. To enable it, copy it to `.github/workflows/checks.yml`; it does not run the PostgreSQL test suite.

## Maintainer

[Jap Dave](https://github.com/JapDave) · Python Backend Developer · [Contact](mailto:japdavev@gmail.com)
