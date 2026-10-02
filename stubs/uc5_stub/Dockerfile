FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
RUN pip install pydantic pydantic-settings redis --no-cache-dir

COPY stubs/uc5_stub/ ./stubs/uc5_stub/

CMD ["python", "stubs/uc5_stub/main.py"]
