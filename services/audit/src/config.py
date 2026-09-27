from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)
    database_url: str = Field(default="", alias="DATABASE_URL")

settings = AuditSettings()