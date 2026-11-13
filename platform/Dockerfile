FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

COPY platform/requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends nginx libgomp1 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install --retries 10 --timeout 120 -r requirements.txt

COPY platform/ .
COPY data/ /app/seed-data/
COPY app.py /app/app.py

EXPOSE 9011

CMD ["sh", "docker/entrypoint-web.sh"]
