"""
Analytics Service — Entry Point
================================

Reads the ``UC_ID`` environment variable and launches the corresponding
UC analytics worker.  Each worker is a subclass of ``BaseConsumer``
that subscribes to Redis streams, fetches frames from MinIO, and emits
alerts via the shared ``AlertPublisher``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))

from services.analytics.src.uc1_worker import UC1Worker
from services.analytics.src.uc2_worker import UC2Worker
from services.analytics.src.uc3_worker import UC3Worker
from services.analytics.src.uc4_worker import UC4Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("analytics")

WORKERS = {
    "uc1": UC1Worker,
    "uc2": UC2Worker,
    "uc3": UC3Worker,
    "uc4": UC4Worker,
}


async def run() -> None:
    uc_id = os.environ.get("UC_ID", "uc1").lower()
    worker_cls = WORKERS.get(uc_id)
    if worker_cls is None:
        logger.error("Unknown UC_ID=%s — valid values: %s", uc_id, list(WORKERS))
        sys.exit(1)

    logger.info("analytics_service_starting uc=%s", uc_id)
    worker = worker_cls()
    await worker.start()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
