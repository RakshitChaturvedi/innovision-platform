from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class AlertManagementSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")

    jwt_secret: str = Field(default="", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"

    alerts_stream: str = "alerts:live"
    dead_letter_stream: str = "alerts:dead_letter"
    notifications_stream: str = "notifications:live"
    consumer_group: str = "alert_management_group"
    consumer_name: str = Field(default="alert_management_worker_1", alias="CONSUMER_NAME")

    incident_trigger_severities: set[str] = {"high", "critical"}

    escalation_level_1_delay_s: int = 120  
    escalation_level_2_delay_s: int = 180  
    escalation_level_3_delay_s: int = 300 

    celery_broker_url: str = Field(default="redis://redis:6379/1", alias="CELERY_BROKER_URL")

settings = AlertManagementSettings()