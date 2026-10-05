FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

COPY shared /app/shared
COPY stubs/uc3_stub/requirements.txt /app/stubs/uc3_stub/requirements.txt

RUN pip install --no-cache-dir -r /app/stubs/uc3_stub/requirements.txt

COPY stubs/uc3_stub /app/stubs/uc3_stub

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["uvicorn", "stubs.uc3_stub.main:app", "--host", "0.0.0.0", "--port", "8023"]