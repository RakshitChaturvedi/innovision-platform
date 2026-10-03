from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices

class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    database_url: str = Field(default="", alias="DATABASE_URL")
    jwt_secret: str = Field(default="", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "ACCESS_TOKEN_EXPIRE_MINUTES"),
    )
    refresh_token_expire_days: int = Field(
        default=7,
        validation_alias=AliasChoices("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "REFRESH_TOKEN_EXPIRE_DAYS", "REFRESH_TOKEN_EXPIRE_DATS"),
    )

settings = AuthSettings()