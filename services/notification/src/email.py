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

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("escalation_email_sent to=%s level=%d", to_email, level)
        return True
    except Exception as e:
        logger.error("escalation_email_failed to=%s level=%d error=%s", to_email, level, e)
        return False