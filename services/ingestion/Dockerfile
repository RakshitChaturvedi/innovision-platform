FROM python:3.13-slim

# Install FFmpeg and OpenCV system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN pip install --no-cache-dir \
    opencv-python-headless \
    numpy \
    pydantic \
    redis \
    minio \
    sqlalchemy[asyncio] \
    asyncpg \
    fastapi \
    uvicorn

COPY shared/ shared/
COPY services/ingestion/ services/ingestion/

ENV APP_ROOT=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8020

CMD ["python", "-m", "services.ingestion.main"]
