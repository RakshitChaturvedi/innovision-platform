import asyncio
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI

from services.notification.src.consumer import NotificationConsumer


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    consumer = NotificationConsumer()

    consumer_task = asyncio.create_task(
        consumer.start()
    )

    logger.info("notification_service_started")

    try:
        yield
    finally:
        consumer_task.cancel()

        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

        logger.info("notification_service_stopped")


app = FastAPI(
    title="Notification Service",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "notification",
    }