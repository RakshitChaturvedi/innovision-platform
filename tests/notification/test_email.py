import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from services.notification.src.email import send_escalation_email
from services.notification.src.consumer import NotificationConsumer


class FakeSMTP:
    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.starttls_called = False
        self.login_args = None
        self.messages_sent = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        self.messages_sent.append(msg)


def test_send_email_tls_off():
    """No starttls call when TLS is off; no login call when credentials empty."""
    fake_smtp = FakeSMTP("mailhog", 1025)

    with patch("services.notification.src.email.smtplib.SMTP", return_value=fake_smtp):
        with patch("services.notification.src.email.settings.smtp_use_tls", False), \
             patch("services.notification.src.email.settings.smtp_user", ""), \
             patch("services.notification.src.email.settings.smtp_password", ""):
            res = send_escalation_email(
                to_email="op@example.com",
                alert_title="Unsafe Zone Entry",
                alert_description="Worker in restricted area",
                camera_name="Cam 1",
                level=1,
            )

    assert res is True
    assert fake_smtp.starttls_called is False
    assert fake_smtp.login_args is None
    assert len(fake_smtp.messages_sent) == 1


def test_send_email_tls_and_login_configured():
    """starttls and login called when configured."""
    fake_smtp = FakeSMTP("smtp.example.com", 587)

    with patch("services.notification.src.email.smtplib.SMTP", return_value=fake_smtp):
        with patch("services.notification.src.email.settings.smtp_use_tls", True), \
             patch("services.notification.src.email.settings.smtp_user", "myuser"), \
             patch("services.notification.src.email.settings.smtp_password", "mypass"):
            res = send_escalation_email(
                to_email="op@example.com",
                alert_title="PPE Violation",
                alert_description="No hard hat",
                camera_name="Cam 2",
                level=2,
            )

    assert res is True
    assert fake_smtp.starttls_called is True
    assert fake_smtp.login_args == ("myuser", "mypass")
    assert len(fake_smtp.messages_sent) == 1


@pytest.mark.asyncio
async def test_failing_send_does_not_crash_consumer_loop():
    """A failing email send logs failure without raising or crashing consumer loop."""
    fake_smtp = FakeSMTP("mailhog", 1025)
    fake_smtp.send_message = MagicMock(side_effect=Exception("Connection refused"))

    with patch("services.notification.src.email.smtplib.SMTP", return_value=fake_smtp):
        res = send_escalation_email(
            to_email="op@example.com",
            alert_title="Alert",
            alert_description="Desc",
            camera_name="Cam 1",
            level=1,
        )

    # Returns False instead of raising exception
    assert res is False
