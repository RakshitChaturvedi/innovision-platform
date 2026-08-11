FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl && \
    rm -rf /var/lib/apt/lists/*

COPY services/camera_registry/requirements.txt ./requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY services/camera_registry/ ./services/camera_registry/

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8011

CMD ["uvicorn","services.camera_registry.main:app","--host","0.0.0.0","--port","8011"]