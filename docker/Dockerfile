FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for caching
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy project
COPY . /app

# Entrypoint
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000
CMD ["bash", "docker/entrypoint.sh"]
