from functools import lru_cache
import json
import os
from typing import Annotated, List, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Flowkron Agent Core"
    environment: str = "local"
    debug: bool = True
    database_url: str = "sqlite:///./flowkron_agent_core.db"
    database_schema: str = "agent_core"
    persistence_mode: str = "operational"
    allow_local_db_bootstrap: bool = False
    operational_service_url: str = "http://flowkron-operational-service:8001"
    cors_allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4200", "http://localhost:8080"]
    )
    baileys_internal_token: str = ""
    internal_token: str = "change-me-local-internal-token"
    jwt_public_key: str = ""
    jwt_public_key_path: str = ""
    jwt_algorithm: str = "RS256"
    jwt_audience: str = "flowkron"
    jwt_issuer: str = "flowkron-auth-service"
    allow_insecure_tenant_header: bool = False
    max_upload_bytes: int = 5_242_880
    allowed_upload_extensions: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: [".pdf", ".docx", ".csv", ".xlsx", ".txt", ".md"]
    )
    low_confidence_threshold: float = 0.35
    chat_provider: Literal["auto", "groq", "local"] = "auto"
    groq_api_key: SecretStr = SecretStr("")
    groq_model: str = "openai/gpt-oss-20b"
    chat_completion_max_tokens: int = 2000
    chat_completion_temperature: float = 0.3
    chat_completion_timeout_seconds: int = 60

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir=os.getenv("FLOWKRON_SETTINGS_DIR"),
        extra="ignore",
    )

    @field_validator("cors_allowed_origins", "allowed_upload_extensions", mode="before")
    @classmethod
    def split_list(cls, value):
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = []
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
