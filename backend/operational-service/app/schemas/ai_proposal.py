from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AIProposalOut(BaseModel):
    id: int
    action_type: str
    resource_type: Literal["contact", "lead", "opportunity", "conversation"]
    resource_id: int
    arguments: dict
    idempotency_key: str
    status: Literal["pending", "approved", "rejected", "executed", "expired"]
    proposal_version: int
    proposed_by: str
    rationale: str | None = None
    correlation_id: str | None = None
    expires_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    executed_by: str | None = None
    executed_at: datetime | None = None
    effect_result: dict | None = None
    created_at: datetime
    updated_at: datetime
    duplicate: bool = False


class AIProposalListResponse(BaseModel):
    items: list[AIProposalOut]
    total: int
    limit: int
    offset: int


class AIProposalCreateIn(BaseModel):
    action_type: str = Field(min_length=1, max_length=64)
    resource_id: int = Field(ge=1)
    arguments: dict
    idempotency_key: str = Field(min_length=1, max_length=180)
    rationale: str | None = Field(default=None, max_length=240)
    expires_at: datetime | None = None


class AIProposalReviewIn(BaseModel):
    expected_version: int = Field(ge=1)
    review_note: str | None = Field(default=None, max_length=240)


class AIProposalExecuteIn(BaseModel):
    expected_version: int | None = Field(default=None, ge=1)
