import asyncio
import logging
import sys

from contextlib import asynccontextmanager
from fastapi import FastAPI

from services.alert_management.src.consumer import AlertConsumer
from services.alert_management.src.websocket import socket_app
from services.alert_management.src.router import router

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = AlertConsumer()
    consumer_task = asyncio.create_task(consumer.start())
    logger.info("alert_management_service_started")

    try:
        yield
    finally:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("alert_management_service_stopped")

app = FastAPI(title="Alert Management Service", lifespan=lifespan)
app.include_router(router)
app.mount("/socket.io", socket_app)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "alert_management"}