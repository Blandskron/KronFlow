from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContactOut(BaseModel):
    id: int
    full_name: str
    email: str | None
    phone: str | None
    source: str
    created_at: datetime


class ContactListResponse(BaseModel):
    items: list[ContactOut]
    total: int
    limit: int
    offset: int


class ContactNameUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(max_length=180)
    expected_full_name: str

    @field_validator("full_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Contact name must not be blank")
        return value.strip()
