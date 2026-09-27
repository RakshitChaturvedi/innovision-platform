"""
Push notification delivery — stubbed in Phase 3.
Interface defined now so Notification Service doesn't need to change
shape when the mobile app (future scope) is built; only this file's
internals change.
"""
import logging

logger = logging.getLogger(__name__)


def send_push_notification(device_token: str, title: str, body: str) -> bool:
    """
    Phase 3: no-op stub. Logs intent so behavior is visible in dev/testing
    without requiring Firebase credentials to be configured.
    """
    logger.info(
        "push_notification_stub device_token=%s title=%s",
        device_token[:8] + "...", title,
    )
    return True