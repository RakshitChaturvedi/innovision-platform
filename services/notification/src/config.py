from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class NotificationSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")

    notifications_stream: str = "notifications:live"
    consumer_group: str = "notification_group"
    consumer_name: str = Field(default="notification_worker_1", alias="CONSUMER_NAME")

    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from: str = Field(default="alerts@innovision.com", alias="SMTP_FROM")

    # Level → role that gets notified
    escalation_role_map: dict[int, str] = {1: "operator", 2: "admin", 3: "superadmin"}

settings = NotificationSettings()