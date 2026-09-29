FROM python:3.11-slim

# System dependencies for OpenCV and curl healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY services/uc2_fire_smoke/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy shared library and UC2 service code
COPY shared /app/shared
COPY services/uc2_fire_smoke /app/services/uc2_fire_smoke

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    UC2_PORT=8030

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8030

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8030/health || exit 1

CMD ["uvicorn", "services.uc2_fire_smoke.src.main:app", "--host", "0.0.0.0", "--port", "8030"]
