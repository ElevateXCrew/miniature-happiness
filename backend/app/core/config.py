from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./alysha_booking.db"

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_sms_number: str = ""
    twilio_whatsapp_number: str = ""
    twilio_validate_signature: bool = True

    # App
    app_env: str = "development"
    secret_key: str = ""
    log_level: str = "INFO"

    # Auth
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_minutes: int = 10080
    seed_admin_email: str = Field(
        default="admin@alysha.local",
        validation_alias=AliasChoices("SEED_ADMIN_EMAIL", "ADMIN_EMAIL"),
    )
    seed_admin_password: str = Field(
        default="admin123",
        validation_alias=AliasChoices("SEED_ADMIN_PASSWORD", "ADMIN_PASSWORD"),
    )
    seed_worker_email: str = Field(
        default="worker@alysha.local",
        validation_alias=AliasChoices("SEED_WORKER_EMAIL", "WORKER_EMAIL"),
    )
    seed_worker_password: str = Field(
        default="worker123",
        validation_alias=AliasChoices("SEED_WORKER_PASSWORD", "WORKER_PASSWORD"),
    )

    # Worker seed
    default_worker_name: str = "Alysha"
    default_worker_timezone: str = "Europe/London"

    # Booking rules
    slot_buffer_minutes: int = 15
    reminder_minutes_before: int = 20

    # Phase 5 reliability
    outbound_retry_max_attempts: int = 3
    outbound_retry_backoff_seconds: int = 30

    # Media storage
    media_storage_root: str = "media"
    media_fetch_timeout_seconds: int = 20


settings = Settings()
