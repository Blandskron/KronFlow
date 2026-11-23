from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConsentEvidenceItem(BaseModel):
    id: int
    kind: Literal["decision", "prior_withdrawal"]
    accepted: bool | None
    effective_at: datetime | None
    recorded_at: datetime
    policy_version: str | None
    source: Literal["whatsapp_message", "operational"] | None


class ContactConsentOut(BaseModel):
    channel: Literal["whatsapp"] = "whatsapp"
    state: Literal["unlinked", "unrecorded", "granted", "not_granted"]
    decision_at: datetime | None
    authorized_from: datetime | None
    policy_version: str | None
    items: list[ConsentEvidenceItem]
    next_before_id: int | None
