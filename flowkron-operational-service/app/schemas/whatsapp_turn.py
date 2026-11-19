from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.schemas.ingest import WhatsAppMessageIn


class TurnClaimIn(WhatsAppMessageIn):
    direction: Literal["inbound"] = "inbound"


class TurnTokenIn(BaseModel):
    claim_token: str = Field(min_length=20, max_length=64)


class TurnPrepareIn(TurnTokenIn):
    reply_body: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    requires_human: bool = False


class TurnReceiptIn(BaseModel):
    provider_message_id: str = Field(min_length=1, max_length=220)
    sent_at: AwareDatetime


class TurnCompleteIn(TurnTokenIn, TurnReceiptIn):
    pass


class TurnOut(BaseModel):
    turn_id: int | None = None
    state: Literal["received", "generating", "prepared", "sending", "completed", "unknown", "cancelled", "legacy_untracked"]
    claimed: bool = False
    claim_token: str | None = None
    lease_until: datetime | None = None
    input_body: str | None = None
    phone: str | None = None
    external_thread_id: str | None = None
    reply_body: str | None = None
    requires_human: bool = False
    outbound_message_id: int | None = None
    last_error: str | None = None
