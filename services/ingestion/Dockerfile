FROM python:3.11-slim

WORKDIR /app

# Install FFmpeg and OpenCV system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY services/ingestion/requirements.txt ./requirements.txt
# Install Python dependencies
RUN pip install --no-cache-dir -r ./requirements.txt

COPY shared/ shared/
COPY services/ingestion/ ./services/ingestion/

ENV APP_ROOT=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8020

CMD ["uvicorn", "services.ingestion.main:app", "--host", "0.0.0.0", "--port", "8020"]
