"""Application configuration via pydantic-settings (Pydantic v2)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables (or .env file)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Database --
    database_url: str | None = None
    cloud_sql_connection_name: str = "claims-project:us-central1:claims-db"
    db_user: str = "fraud_user"
    db_password: str = ""
    db_name: str = "claims"

    # -- GCS --
    gcs_bucket: str = "claims-photos"

    # -- Gemini --
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # -- Auth / Sessions --
    session_secret: str = "change-me-in-production"
    session_timeout_minutes: int = 60

    # -- CORS --
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    # -- App --
    debug: bool = False
    environment: str = "development"


settings = Settings()
