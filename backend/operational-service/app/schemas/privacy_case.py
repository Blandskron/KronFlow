from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


CaseState = Literal["pendiente", "en_proceso", "completada"]
CaseKind = Literal["acceso", "rectificacion", "eliminacion", "oposicion", "portabilidad", "bloqueo"]


class PrivacyCaseCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: CaseKind
    contact_id: int | None = None
    email: str | None = None
    whatsapp_id: str | None = None
    notas: str | None = None


class PrivacyRectifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = None
    email: str | None = None
    telefono: str | None = None


class PrivacyRestrictIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    restricted: bool = True
    reason: str | None = None


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
    messages: list[dict] = []
    consent_decisions: list[dict] = []
    consent_receipts: list[dict] = []
    suppressions: list[dict] = []
    memory_items: list[dict] = []
    attachments: list[dict] = []
    voice_transcripts: list[dict] = []
    commerce_orders: list[dict] = []
    webchat_sessions_count: int = 0
    external_mappings_count: int = 0
    workflow_runs_count: int = 0
    voice_calls_count: int = 0
    commerce_orders_count: int = 0


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
    memory_items_deleted: int = 0
    attachments_deleted: int = 0
    webchat_sessions_anonymized: int = 0
    workflow_runs_cancelled: int = 0
    voice_segments_redacted: int = 0
    email_suppressions_recorded: int = 0
    conversations_redacted: int = 0
    leads_redacted: int = 0
    activities_redacted: int = 0
    proposals_redacted: int = 0
    domain_events_redacted: int = 0
    external_mappings_deleted: int = 0


class RetentionSweepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_retention_days: int


class RetentionSweepOut(BaseModel):
    message_retention_days: int
    messages_deleted: int
    cleanup_log_id: int
    swept_at: datetime


class TenantAIPolicyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_enabled: bool = True
    allow_external_ai_transfer: bool | None = None
    memory_auto_capture: bool | None = None
    reason: str | None = None


class TenantAIPolicyOut(BaseModel):
    ai_enabled: bool
    allow_external_ai_transfer: bool = False
    memory_auto_capture: bool = False
    updated_by: str | None = None
    reason: str | None = None
    updated_at: datetime | None = None
    cancelled_ai_turns: int = 0


class TenantRetentionPolicyUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages_retention_days: int = 180
    memory_retention_days: int = 90
    attachments_retention_days: int = 90
    voice_retention_days: int = 90
    traces_retention_days: int = 90
    webchat_retention_days: int = 90
    legal_hold: bool = False
    legal_hold_reason: str | None = None


class TenantRetentionPolicyOut(BaseModel):
    messages_retention_days: int = 180
    memory_retention_days: int = 90
    attachments_retention_days: int = 90
    voice_retention_days: int = 90
    traces_retention_days: int = 90
    webchat_retention_days: int = 90
    legal_hold: bool = False
    legal_hold_reason: str | None = None
    last_swept_at: datetime | None = None
    updated_by: str | None = None
    updated_at: datetime | None = None


class SubprocessorApprovalIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    subprocessor_list_version: str = "2026-11-v1"


class SecurityIncidentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["low", "medium", "high", "critical"]
    title: str
    summary: str
    affected_records_estimate: int = 0
    detected_at: datetime | None = None
    containment_notes: str | None = None


class SecurityIncidentUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["open", "contained", "notified", "closed"] | None = None
    containment_notes: str | None = None

