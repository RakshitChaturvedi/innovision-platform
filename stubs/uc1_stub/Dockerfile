FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
RUN pip install pydantic pydantic-settings redis --no-cache-dir

COPY stubs/uc1_stub/ ./stubs/uc1_stub/

CMD ["python", "stubs/uc1_stub/main.py"]