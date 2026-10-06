FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Install torch CPU-only FIRST — pinned so ultralytics doesn't re-resolve GPU build
RUN pip install --no-cache-dir --timeout 60 --retries 10 \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY shared /app/shared
COPY stubs/uc3_stub/requirements.txt /app/stubs/uc3_stub/requirements.txt

RUN pip install --no-cache-dir -r /app/stubs/uc3_stub/requirements.txt

COPY stubs/uc3_stub /app/stubs/uc3_stub
COPY tests /app/tests

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["uvicorn", "stubs.uc3_stub.main:app", "--host", "0.0.0.0", "--port", "8023"]