from functools import lru_cache
import json
import os
import re
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Flowkron Operational Service"
    environment: str = "local"
    debug: bool = True

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/flowkron_auth"
    database_schema: str = "operational"
    database_grant_role: str = ""
    cors_allowed_origins: Annotated[List[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:4200", "http://localhost:8080"]
    )

    baileys_internal_token: str = ""
    internal_token: str = ""
    jwt_public_key: str = ""
    jwt_public_key_path: str = ""
    jwt_algorithm: str = "RS256"
    jwt_audience: str = "flowkron"
    jwt_issuer: str = "flowkron-auth-service"

    default_page_size: int = 50
    max_page_size: int = 200
    tenant_migration_version: str = "tenant_schema_v8"
    ingest_rate_limit_per_minute: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        secrets_dir=os.getenv("FLOWKRON_SETTINGS_DIR"),
        extra="ignore",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value):
        if isinstance(value, (list, tuple, set)):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    parsed = []
                if isinstance(parsed, list):
                    return [str(origin).strip() for origin in parsed if str(origin).strip()]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str) and value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @field_validator("database_schema")
    @classmethod
    def validate_database_schema(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError("DATABASE_SCHEMA must be a valid PostgreSQL identifier.")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
