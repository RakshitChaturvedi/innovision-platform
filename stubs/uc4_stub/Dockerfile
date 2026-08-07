FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
RUN pip install pydantic pydantic-settings redis --no-cache-dir

COPY stubs/uc4_stub/ ./stubs/uc4_stub/

CMD ["python", "stubs/uc4_stub/main.py"]