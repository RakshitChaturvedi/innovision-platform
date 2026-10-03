from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class CameraRegistrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    internal_service_key: str = Field(default="", alias="INTERNAL_SERVICE_KEY")


settings = CameraRegistrySettings()
