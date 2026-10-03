FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY shared/ ./shared/
RUN pip install --no-cache-dir pydantic pydantic-settings redis opencv-python-headless fastapi uvicorn minio

COPY stubs/uc3_stub/ ./stubs/uc3_stub/

EXPOSE 8031

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8031/health || exit 1

CMD ["python", "stubs/uc3_stub/main.py"]