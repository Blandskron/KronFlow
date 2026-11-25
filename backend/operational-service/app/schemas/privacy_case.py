from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


CaseState = Literal["pendiente", "en_proceso", "completada"]
CaseKind = Literal["acceso", "rectificacion", "eliminacion", "oposicion", "portabilidad"]


class PrivacyCaseOut(BaseModel):
    id: int
    kind: CaseKind
    state: CaseState
    requested_at: datetime
    due_at: datetime
    completed_at: datetime | None


class PrivacyCasePage(BaseModel):
    items: list[PrivacyCaseOut]
    total: int
    limit: int
    offset: int


class PrivacyCaseTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_state: Literal["pendiente", "en_proceso"]
    state: Literal["en_proceso", "completada"]
    confirmed: bool = False


class PrivacyCaseExportOut(BaseModel):
    case_id: int
    kind: str
    exported_at: datetime
    subject_contact: dict | None = None
    contact_points: list[dict] = []
    leads: list[dict] = []
    opportunities: list[dict] = []
    message_count: int = 0
    consent_decisions: list[dict] = []
    suppressions: list[dict] = []


class PrivacyErasureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool = False


class PrivacyErasureOut(BaseModel):
    case_id: int
    state: CaseState
    clients_anonymized: int
    messages_redacted: int
    contact_points_deleted: int
    suppression_recorded: bool
    cleanup_log_id: int


class RetentionSweepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_retention_days: int


class RetentionSweepOut(BaseModel):
    message_retention_days: int
    messages_deleted: int
    cleanup_log_id: int
    swept_at: datetime

