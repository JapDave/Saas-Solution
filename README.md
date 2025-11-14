## Setup & run

### Docker (recommended)

```bash
# 1) Copy project, then:
cp .env.example .env

# 2) (Optional) auto-create superuser on boot
# In .env:
# AUTO_CREATE_SUPERUSER=1
# DJANGO_SUPERUSER_USERNAME=admin
# DJANGO_SUPERUSER_EMAIL=admin@example.com
# DJANGO_SUPERUSER_PASSWORD=admin123

# 3) Start
docker compose -f docker/compose.yaml up --build
```

Endpoints:
- Swagger: `http://localhost:8000/api/docs`  
- Redoc:   `http://localhost:8000/api/redoc`  
- Admin:   `http://localhost:8000/admin/`


> Static files: **WhiteNoise** + `collectstatic` is wired in the entrypoint so admin/Swagger assets are served even under Gunicorn.

### Local (venv) — optional

```bash
python -m venv .venv
source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

cp .env.example .env        # adjust DB vars for your local Postgres

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

---

## For running Test Cases
docker compose -f docker/compose.yaml run --rm web pytest -q

## Channel Module

Run `python manage.py initialize_roles` once to seed base roles, then `python manage.py migrate` and use `/api/organizations/<org_uuid>/channels/` endpoints to manage channel instances. For demo data (accounts, orgs, channels, agents) run `python manage.py seed_demo_data --with-roles`.

## Flows Module

Flows management follows the same org-scoped pattern:
- Run `python manage.py initialize_roles` to ensure the Agent Manager role carries all `agents:flows:*` permissions.
- Hit `/api/organizations/<org_uuid>/flows/` for CRUD and `/api/organizations/<org_uuid>/flows/{flow_uuid}/versions/` for version saves/history.
- Demo data includes a published onboarding flow once you run `python manage.py seed_demo_data --with-roles`.

## Integrations Module

- Permissions (`integrations:*`) ride on the same Agent Manager role; re-run `python manage.py initialize_roles` after pulling.
- CRUD lives under `/api/organizations/<org_uuid>/integrations/` with actions for activate/deactivate, `/test`, and `/regenerate-secret` (webhooks only).
- Analytics endpoints: `/integrations/analytics/` (org-level) and `/integrations/{uuid}/analytics/` (single integration).
- Demo data seeds one API integration and one webhook so you can see the payloads immediately.
