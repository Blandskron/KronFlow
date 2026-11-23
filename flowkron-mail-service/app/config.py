from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class SenderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_address: str = Field(alias="from", min_length=3, max_length=320)
    reply_to: str | None = Field(default=None, max_length=320)


class ClientConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=8, max_length=500)
    allowed_senders: list[str] = Field(min_length=1)
    active: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    app_env: str = "development"
    port: int = 8000
    log_level: str = "INFO"
    resend_api_key: str = ""
    resend_base_url: str = "https://api.resend.com"
    resend_timeout_seconds: float = 20
    resend_webhook_secret: str = ""
    email_senders_json: dict[str, SenderConfig] = Field(default_factory=dict)
    internal_clients_json: dict[str, ClientConfig] = Field(default_factory=dict)
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    enable_legacy_mail_endpoint: bool = False
    redis_url: str = ""

    @property
    def senders(self) -> dict[str, SenderConfig]:
        return self.email_senders_json

    @property
    def clients(self) -> dict[str, ClientConfig]:
        return self.internal_clients_json


class ConfigurationError(RuntimeError):
    pass


def validate_runtime_settings(settings: Settings, *, production: bool | None = None) -> None:
    is_production = production if production is not None else settings.app_env.lower() == "production"
    valid_base = settings.resend_base_url.lower().startswith("https://")
    if is_production and (not settings.resend_api_key or not valid_base or not settings.senders or not settings.clients):
        raise ConfigurationError("La configuración del proveedor de correo está incompleta.")
    if settings.rate_limit_requests < 1 or settings.rate_limit_window_seconds < 1:
        raise ConfigurationError("La configuración del proveedor de correo está incompleta.")
    for key, sender in settings.senders.items():
        if "\r" in sender.from_address or "\n" in sender.from_address or (sender.reply_to and ("\r" in sender.reply_to or "\n" in sender.reply_to)):
            raise ConfigurationError(f"Configuración inválida para sender_key '{key}'.")
    for key, client in settings.clients.items():
        if not client.api_key or not client.allowed_senders:
            raise ConfigurationError(f"Configuración inválida para cliente '{key}'.")


@lru_cache
def get_settings() -> Settings:
    try:
        settings = Settings()
        validate_runtime_settings(settings)
        return settings
    except (ValidationError, ValueError, ConfigurationError) as exc:
        raise ConfigurationError("La configuración del proveedor de correo está incompleta.") from exc
