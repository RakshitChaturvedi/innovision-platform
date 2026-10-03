import pytest
from services.auth.src.config import AuthSettings


def test_auth_settings_aliases(monkeypatch):
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "14")

    settings = AuthSettings()
    assert settings.access_token_expire_minutes == 30
    assert settings.refresh_token_expire_days == 14
