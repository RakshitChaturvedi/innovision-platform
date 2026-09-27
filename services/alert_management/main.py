import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.alert_management.src.consumer import AlertConsumer
from services.alert_management.src.websocket import sio
from services.alert_management.src.router import router


logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

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


fastapi_app = FastAPI(
    title="Alert Management Service",
    lifespan=lifespan,
)

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

fastapi_app.include_router(router)


@fastapi_app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "alert_management",
    }


app = socketio.ASGIApp(
    socketio_server=sio,
    other_asgi_app=fastapi_app,
)