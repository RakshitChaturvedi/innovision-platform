FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
RUN pip install pydantic pydantic-settings redis --no-cache-dir

COPY stubs/uc3_stub/ ./stubs/uc3_stub/

CMD ["python", "stubs/uc3_stub/main.py"]