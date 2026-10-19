import os
from pathlib import Path
from dotenv import load_dotenv

# Load root .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Ensure local test database URL points to 127.0.0.1:5433
os.environ["DATABASE_URL_LOCAL"] = "postgresql+asyncpg://innovision:changeme@127.0.0.1:5433/innovision_platform"
os.environ["REDIS_LOCAL_URL"] = "redis://127.0.0.1:6379"
