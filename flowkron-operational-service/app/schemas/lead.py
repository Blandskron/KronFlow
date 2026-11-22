from datetime import datetime

from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator

LeadStage = Literal["nuevo", "contactado", "en_proceso", "ganado", "perdido"]


class LeadOut(BaseModel):
    id: int
    full_name: str
    phone: str
    email: str
    source: str
    direction: str
    temperature: str
    lifecycle_status: str
    assigned_to_user_id: int | None
    score: int
    tags: list
    metadata: dict
    created_at: datetime
    updated_at: datetime


class LeadUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=180)
    email: str | None = Field(default=None, max_length=180)
    direction: str | None = Field(default=None, max_length=24)
    temperature: str | None = Field(default=None, max_length=24)
    lifecycle_status: LeadStage | None = None
    expected_updated_at: AwareDatetime | None = None
    assigned_to_user_id: int | None = Field(default=None, ge=1, le=2147483647)
    score: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = None
    metadata: dict | None = None

    @field_validator("lifecycle_status", "score", "temperature")
    @classmethod
    def validate_update_value(cls, value):
        if value is None:
            raise ValueError("This field cannot be set to null")
        return value

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: str) -> str:
        if value not in {"cold", "warm", "hot", "frio", "tibio", "caliente"}:
            raise ValueError("Unknown lead classification")
        return value


class LeadListResponse(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int

