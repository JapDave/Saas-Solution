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