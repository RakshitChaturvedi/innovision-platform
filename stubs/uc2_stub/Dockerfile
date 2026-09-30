FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/uc2_fire_smoke/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY shared/ /app/shared/
COPY services/uc2_fire_smoke/ /app/services/uc2_fire_smoke/
COPY stubs/uc2_stub/ /app/stubs/uc2_stub/

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "services.uc2_fire_smoke.src.main:app", "--host", "0.0.0.0", "--port", "8030"]