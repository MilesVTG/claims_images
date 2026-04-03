"""Worker configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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

    # -- Cloud Vision --
    enable_cloud_vision: bool = True

    # -- Exchange Email --
    exchange_email: str = ""
    exchange_password: str = ""
    exchange_server: str = ""
    alert_recipients: str = ""
    high_risk_threshold: float = 80.0
    dashboard_base_url: str = "http://localhost:3000"

    # -- App --
    debug: bool = False
    environment: str = "development"


settings = Settings()
