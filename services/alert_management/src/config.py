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

    # MinIO settings for presigned snapshot URLs
    minio_endpoint: str = Field(default="minio:9000", alias="MINIO_ENDPOINT")
    minio_public_endpoint: str = Field(default="localhost:9000", alias="MINIO_PUBLIC_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    minio_snapshots_bucket: str = "innovision-snapshots"
    snapshot_presign_expires: int = 300  # seconds

settings = AlertManagementSettings()