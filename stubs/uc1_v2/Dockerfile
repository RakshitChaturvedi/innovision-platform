FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        curl && \
    rm -rf /var/lib/apt/lists/*

COPY stubs/uc1_v2/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY stubs/uc1_v2/ .

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8021" ]