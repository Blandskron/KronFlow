from datetime import datetime

from pydantic import BaseModel, Field


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
    lifecycle_status: str | None = Field(default=None, max_length=32)
    assigned_to_user_id: int | None = None
    score: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = None
    metadata: dict | None = None


class LeadListResponse(BaseModel):
    items: list[LeadOut]
    total: int
    limit: int
    offset: int

