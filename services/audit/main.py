import logging
import sys
from fastapi import FastAPI
from services.audit.src.router import router, settings_router

logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

app = FastAPI(title="Audit & Settings Service")
app.include_router(router)
app.include_router(settings_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "audit_and_settings"}