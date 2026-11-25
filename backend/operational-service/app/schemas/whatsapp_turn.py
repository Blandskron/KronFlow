from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from app.schemas.ingest import WhatsAppMessageIn


class TurnClaimIn(WhatsAppMessageIn):
    direction: Literal["inbound"] = "inbound"


class TurnTokenIn(BaseModel):
    claim_token: str = Field(min_length=20, max_length=64)


class TurnSendIn(TurnTokenIn):
    provider_message_id: str | None = Field(default=None, min_length=1, max_length=220)


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


AccountKey = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
RecipientJid = Annotated[str, Field(max_length=180, pattern=r"^[0-9]+@(s\.whatsapp\.net|lid)$")]
ProviderFailureReason = Literal["provider_rejected", "account_restricted", "connection_invalid"]


class TurnEnqueueIn(TurnClaimIn):
    account_key: AccountKey
    recipient_jid: RecipientJid
    body: str = Field(min_length=1, max_length=4000, pattern=r"\S")
    sent_at: AwareDatetime

    @model_validator(mode="after")
    def check_recipient(self):
        if not self.phone.isascii() or not self.phone.isdecimal() or not 7 <= len(self.phone) <= 15:
            raise ValueError("Expected a normalized WhatsApp phone")
        if self.recipient_jid.endswith("@s.whatsapp.net") and self.recipient_jid != f"{self.phone}@s.whatsapp.net":
            raise ValueError("Recipient does not match the message phone")
        if self.body.strip().upper() in {"ACEPTO", "BAJA"}:
            raise ValueError("Consent commands use the consent endpoint")
        return self


class TurnEnqueueOut(BaseModel):
    turn_id: int | None = None
    disposition: Literal["accepted", "duplicate", "legacy_untracked"]


class TurnNextIn(BaseModel):
    account_key: AccountKey


class ClaimedTurnJob(TurnOut):
    recipient_jid: str


class TurnNextOut(BaseModel):
    job: ClaimedTurnJob | None = None


class ProviderReceiptIn(BaseModel):
    account_key: AccountKey
    connection_id: Literal["default"] = "default"
    provider_message_id: str = Field(min_length=1, max_length=220)
    recipient_jids: list[RecipientJid] = Field(min_length=1, max_length=2)
    status: Literal["sent", "failed", "delivered", "read"]
    failure_reason: ProviderFailureReason | None = None

    @model_validator(mode="after")
    def check_failure_reason(self):
        if self.failure_reason is not None and self.status != "failed":
            raise ValueError("Failure reason requires failed status")
        return self


class ProviderReceiptsIn(BaseModel):
    receipts: list[ProviderReceiptIn] = Field(min_length=1, max_length=32)


class ProviderReceiptsOut(BaseModel):
    applied: int
