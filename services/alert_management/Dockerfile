FROM python:3.11-slim

WORKDIR /app

COPY shared/ ./shared/
COPY services/alert_management/main.py ./main.py

RUN pip install pydantic pydantic-settings fastapi uvicorn sqlalchemy asyncpg redis --no-cache-dir

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8010"]