from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class PipelineStageOut(BaseModel):
    id: int
    slug: str
    name: str
    position: int
    stage_kind: Literal["open", "won", "lost"]
    is_active: bool
    created_at: datetime


class PipelineStageCreateIn(BaseModel):
    slug: str = Field(min_length=2, max_length=48)
    name: str = Field(min_length=1, max_length=80)
    position: int = Field(ge=0)
    stage_kind: Literal["open", "won", "lost"] = "open"


class PipelineStageListResponse(BaseModel):
    items: list[PipelineStageOut]


class OpportunityActivityOut(BaseModel):
    id: int
    opportunity_id: int
    activity_type: str
    actor_user_id: str | None = None
    from_stage_id: int | None = None
    to_stage_id: int | None = None
    note: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class OpportunityOut(BaseModel):
    id: int
    contact_id: int
    lead_id: int | None = None
    conversation_id: int | None = None
    stage_id: int
    stage_slug: str
    stage_name: str
    stage_kind: Literal["open", "won", "lost"]
    title: str
    owner_user_id: str | None = None
    amount: Decimal | None = None
    currency: str
    outcome: Literal["open", "won", "lost"]
    close_reason: str | None = None
    version: int
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    activities: list[OpportunityActivityOut] | None = None


class OpportunityListResponse(BaseModel):
    items: list[OpportunityOut]
    total: int
    limit: int
    offset: int


class OpportunityCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    contact_id: int | None = Field(default=None, ge=1)
    lead_id: int | None = Field(default=None, ge=1)
    conversation_id: int | None = Field(default=None, ge=1)
    stage_id: int | None = Field(default=None, ge=1)
    owner_user_id: str | None = Field(default=None, max_length=64)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class OpportunityUpdateIn(BaseModel):
    expected_version: int = Field(ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=160)
    stage_id: int | None = Field(default=None, ge=1)
    owner_user_id: str | None = Field(default=None, max_length=64)
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    outcome: Literal["open", "won", "lost"] | None = None
    close_reason: str | None = Field(default=None, max_length=240)
    note: str | None = Field(default=None, max_length=2000)


class OpportunityActivityCreateIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
