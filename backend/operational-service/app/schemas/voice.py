"""Pydantic schemas for voice/telephony call sessions, segments, handoff, and Twilio webhooks."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VoiceCallCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["twilio", "stub"] = "stub"
    external_call_id: str = Field(min_length=2, max_length=160)
    direction: Literal["inbound", "outbound"] = "inbound"
    from_number: str = Field(min_length=3, max_length=40)
    to_number: str = Field(min_length=3, max_length=40)
    client_id: int | None = Field(default=None, ge=1)
    conversation_id: int | None = Field(default=None, ge=1)
    agent_revision_id: int | None = Field(default=None, ge=1)
    recording_consent: bool = False


class VoiceCallSegmentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_no: int = Field(ge=1)
    speaker: Literal["caller", "agent", "operator"]
    transcript: str = Field(min_length=1, max_length=4000)
    started_ms: int = Field(default=0, ge=0)
    ended_ms: int = Field(default=0, ge=0)
    is_barge_in: bool = False


class VoiceCallTransferIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=2, max_length=120)


class VoiceCallCompleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "no_answer", "voicemail", "failed"] = "completed"
    billable_seconds: int = Field(default=0, ge=0)
    estimated_cost_usd: str = Field(default="0")
    recording_attachment_id: int | None = Field(default=None, ge=1)
    close_reason: str | None = Field(default=None, max_length=120)


class VoiceCallSegmentOut(BaseModel):
    id: int
    call_id: int
    sequence_no: int
    speaker: str
    transcript: str
    message_id: int | None = None
    started_ms: int
    ended_ms: int
    is_barge_in: bool
    created_at: datetime


class VoiceCallOut(BaseModel):
    id: int
    provider: str
    external_call_id: str
    direction: str
    from_number: str
    to_number: str
    client_id: int | None = None
    conversation_id: int | None = None
    agent_revision_id: int | None = None
    status: str
    billable_seconds: int
    estimated_cost_usd: str
    recording_consent: bool
    recording_attachment_id: int | None = None
    barge_in_count: int
    close_reason: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    segments: list[VoiceCallSegmentOut] = []
