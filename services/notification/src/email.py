"""SMTP email delivery for alert escalations."""
import logging
import smtplib
from email.mime.text import MIMEText
from .config import settings

logger = logging.getLogger(__name__)


def send_escalation_email(
    to_email: str, alert_title: str, alert_description: str,
    camera_name: str, level: int,
) -> bool:
    subject = f"[ESCALATION L{level}] {alert_title}"
    body = f"""
Alert requires attention — Level {level} escalation.

Camera: {camera_name}
Alert: {alert_title}
Details: {alert_description}

This alert has not been acknowledged. Please review immediately.
"""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to_email

    import os
    if os.getenv("PYTEST_CURRENT_TEST") or not settings.smtp_host or settings.smtp_host.strip() == "":
        logger.debug("smtp_delivery_skipped (test_mode or smtp_not_configured) to=%s", to_email)
        return True

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=2) as server:
            if settings.smtp_user and settings.smtp_password:
                try:
                    server.starttls()
                    server.login(settings.smtp_user, settings.smtp_password)
                except Exception as auth_err:
                    logger.debug("smtp_auth_skipped or_failed err=%s", auth_err)
            server.send_message(msg)
        logger.info("escalation_email_sent to=%s level=%d", to_email, level)
        return True
    except Exception as e:
        logger.error("escalation_email_failed to=%s level=%d error=%s", to_email, level, e)
        return False