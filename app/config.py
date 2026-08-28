"""
Application configuration, loaded from environment variables / .env file.
Never hardcode secrets here — that was the whole problem with the old
static-HTML approach where the API key shipped inside public JS.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+psycopg://gymuser:gympass@localhost:5432/gymtracker"

    # --- Auth / JWT ---
    jwt_secret_key: str  # required, no default — must be set explicitly per environment
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 30

    # --- Admin ---
    admin_email: str
    admin_create_user_key: str  # gate for any future admin-only endpoints

    # --- Email (SMTP) ---
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str  # use a Gmail App Password, not your real password
    smtp_from: str = "Gym Tracker <no-reply@example.com>"

    # --- App URLs (used inside emails, redirects) ---
    site_base_url: str = "http://localhost:8000"

    # --- Environment ---
    environment: str = "development"  # "development" | "production"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Cached so we don't re-parse env vars on every request."""
    return Settings()
