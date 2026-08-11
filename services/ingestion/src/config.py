"""
Centralised configuration for the Ingestion Service.

All tunables are loaded from environment variables with sensible defaults.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class IngestionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")

    database_url: str = Field(default="", alias="DATABASE_URL")

    minio_endpoint: str = Field(default="minio:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")

    # Test mode — reused from UC pattern for local dev without real cameras
    test_mode: bool = Field(default=True, alias="INGESTION_TEST_MODE")
    test_video_path: str = Field(default="", alias="INGESTION_TEST_VIDEO_PATH")

    default_fps: float = Field(default=10, alias="DEFAULT_FPS")
    jpeg_quality: int = Field(default=85, alias="JPEG_QUALITY")
    heartbeat_interval_s: int = Field(default=5, alias="HEARTBEAT_INTERVAL_S")
    stream_maxlen: int = Field(default=1000, alias="STREAM_MAXLEN")
    camera_offline_timeout_s: int = Field(default=10, alias="CAMERA_OFFLINE_TIMEOUT_S")
    frame_cache_ttl_s: int = Field(default=20, alias="FRAME_CACHE_TTL_S")

    # Reconnect backoff
    reconnect_base_delay_s: float = Field(default=1.0, alias="RECONNECT_BASE_DELAY_S")
    reconnect_max_delay_s: float = Field(default=30.0, alias="RECONNECT_MAX_DELAY_S")

    camera_registry_url: str = Field(
        default="http://camera_registry:8011", alias="CAMERA_REGISTRY_URL"
    )
    camera_refresh_interval_s: int = Field(
        default=60, alias="CAMERA_REFRESH_INTERVAL_S"
    )
    minio_frames_bucket: str = "innovision-frames"
    minio_secure: bool = False

settings = IngestionConfig()
