import logging
import sys
from fastapi import FastAPI
from services.reporting.src.router import router

logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

app = FastAPI(title="Reporting Service")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "reporting"}