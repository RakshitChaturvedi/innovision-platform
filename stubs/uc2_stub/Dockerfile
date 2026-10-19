FROM python:3.11-slim

# System deps for OpenCV and image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --timeout 60 --retries 10 \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --index-url ${TORCH_INDEX_URL}

# Install remaining Python dependencies (torch already satisfied from above)
RUN pip install --no-cache-dir --timeout 60 --retries 10 \
    pydantic \
    pydantic-settings \
    redis \
    fastapi \
    uvicorn \
    httpx \
    minio \
    numpy \
    opencv-python-headless \
    ultralytics

# Copy shared platform contracts/clients
COPY shared/ ./shared/

# Copy UC2 stub
COPY stubs/__init__.py ./stubs/__init__.py
COPY stubs/uc2_stub/ ./stubs/uc2_stub/

EXPOSE 8022

CMD ["python", "-m", "uvicorn", "stubs.uc2_stub.main:app", "--host", "0.0.0.0", "--port", "8022"]