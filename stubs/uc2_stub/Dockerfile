FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
RUN pip install pydantic pydantic-settings redis --no-cache-dir

COPY stubs/uc2_stub/ ./stubs/uc2_stub/

CMD ["python", "stubs/uc2_stub/main.py"]