import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.getenv("DJANGO_SETTINGS_MODULE", "config.settings.dev"))

# Keep WSGI lean; request tracing is handled by our custom middleware (apps.common.middlewares.tracing)
application = get_wsgi_application()
