FROM python:3.11-slim

# System deps for OpenCV, PaddleOCR, and image processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install torch CPU-only FIRST — pinned so ultralytics doesn't re-resolve
# a GPU build. Must come before any package that depends on torch.
RUN pip install --no-cache-dir --timeout 60 --retries 10 \
    torch==2.5.1 \
    torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

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
    sqlalchemy[asyncio] \
    asyncpg \
    ultralytics \
    paddlepaddle \
    paddleocr \
    supervision \
    deep-sort-realtime

# Copy shared platform contracts/clients
COPY shared/ ./shared/

# Copy UC4 stub
COPY stubs/__init__.py ./stubs/__init__.py
COPY stubs/uc4_stub/ ./stubs/uc4_stub/

EXPOSE 8024

CMD ["python", "-m", "uvicorn", "stubs.uc4_stub.main:app", "--host", "0.0.0.0", "--port", "8024"]