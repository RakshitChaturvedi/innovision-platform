FROM python:3.13-slim

# OpenCV system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
RUN pip install --no-cache-dir \
    opencv-python-headless \
    numpy \
    pydantic \
    redis \
    minio \
    sqlalchemy[asyncio] \
    asyncpg

COPY shared/ shared/
COPY services/analytics/ services/analytics/

ENV APP_ROOT=/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.analytics.main"]
