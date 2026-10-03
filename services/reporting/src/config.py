from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class ReportingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(default="", alias="DATABASE_URL")

    minio_endpoint: str = Field(default="minio:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    reports_bucket: str = "innovision-reports"

    celery_broker_url: str = Field(
        default="redis://redis:6379/2", alias="CELERY_BROKER_URL"
    )

    # Per-use-case compliance source URLs — all configurable via environment
    uc1_compliance_url: str = Field(
        default="http://uc1_api:8000/uc1/compliance/readiness",
        alias="UC1_COMPLIANCE_URL",
    )
    uc2_compliance_url: str = Field(
        default="http://uc2_api:8000/uc2/compliance/summary",
        alias="UC2_COMPLIANCE_URL",
    )
    uc3_ppe_metrics_url: str = Field(
        default="http://host.docker.internal:8030/uc3/compliance/ppe-summary",
        alias="UC3_PPE_METRICS_URL",
    )
    uc4_compliance_url: str = Field(
        default="http://uc4_api:8000/uc4/compliance/summary",
        alias="UC4_COMPLIANCE_URL",
    )


settings = ReportingSettings()