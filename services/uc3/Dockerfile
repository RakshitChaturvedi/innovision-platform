FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

COPY services/uc3/requirements.txt /app/services/uc3/requirements.txt
RUN pip install --no-cache-dir -r /app/services/uc3/requirements.txt

COPY shared /app/shared
COPY services/uc3 /app/services/uc3

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "services.uc3.main:app", "--host", "0.0.0.0", "--port", "8023"]
