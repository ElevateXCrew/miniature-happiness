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
    seed_admin_email: str = "admin@alysha.local"
    seed_admin_password: str = "admin123"
    seed_worker_email: str = "worker@alysha.local"
    seed_worker_password: str = "worker123"

    # Worker seed
    default_worker_name: str = "Alysha"
    default_worker_timezone: str = "Europe/London"

    # Booking rules
    slot_buffer_minutes: int = 15
    reminder_minutes_before: int = 20

    # Phase 5 reliability
    outbound_retry_max_attempts: int = 3
    outbound_retry_backoff_seconds: int = 30


settings = Settings()
