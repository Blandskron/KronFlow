from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WhatsAppMessageIn(BaseModel):
    external_message_id: str = Field(min_length=1, max_length=220)
    connection_id: Literal["default"] = "default"
    provider_message_id: str | None = Field(default=None, min_length=1, max_length=220)
    message_type: Literal["text"] = "text"
    delivery_status: Literal["unknown", "received", "sent", "failed"] | None = None
    external_thread_id: str | None = Field(default=None, max_length=180)
    phone: str = Field(min_length=4, max_length=48)
    full_name: str = Field(default="", max_length=180)
    email: str = Field(default="", max_length=180)
    direction: Literal["inbound", "outbound"] = "inbound"
    body: str = ""
    channel: Literal["whatsapp"] = "whatsapp"
    sent_at: datetime
    raw_payload: dict = Field(default_factory=dict)


class LeadClassificationIn(BaseModel):
    phone: str = Field(min_length=4, max_length=48)
    direction: Literal["inbound", "outbound"] | None = None
    temperature: Literal["cold", "warm", "hot"] | None = None
    lifecycle_status: str | None = Field(default=None, max_length=32)
    score: int | None = Field(default=None, ge=0, le=100)
    tags: list[str] | None = None
    metadata: dict = Field(default_factory=dict)


class HandoffIn(BaseModel):
    phone: str = Field(min_length=4, max_length=48)
    external_thread_id: str | None = Field(default=None, max_length=180)
    reason: str = ""
    assigned_to_user_id: int | None = None


class WhatsAppStatusIn(BaseModel):
    external_thread_id: str = Field(min_length=1, max_length=180)
    status: str = Field(min_length=1, max_length=32)


class ConsentIn(BaseModel):
    phone: str = Field(min_length=4, max_length=48)
    accepted: bool = True
    channel: str = Field(default="whatsapp", max_length=40)
    policy_version: str = Field(default="v1.0", max_length=40)


class ConsentOut(BaseModel):
    phone: str
    consentimiento_datos: bool = False
    fecha_consentimiento: datetime | None = None


class CustomerOut(BaseModel):
    id: int | None = None
    rut: str | None = None
    nombre: str | None = None
    email: str | None = None
    telefono: str | None = None
    whatsapp_id: str | None = None


class ClientUpsertIn(BaseModel):
    rut: str = Field(min_length=1, max_length=80)
    nombre: str = Field(min_length=1, max_length=180)
    email: str | None = Field(default=None, max_length=180)
    phone: str = Field(min_length=4, max_length=48)
    consentimiento_datos: bool = True


class ClientUpsertResponse(BaseModel):
    id: int


class LeadUpsertIn(BaseModel):
    cliente_id: int = Field(gt=0)
    score: int = Field(default=0, ge=0, le=115)
    clasificacion: Literal["caliente", "tibio", "frio"] = "frio"
    plazo_compra: Literal["este_dia", "esta_semana", "este_mes", "tres_meses", "cotizando", "explorando"] | None = None
    requiere_credito: bool = False
    estado: Literal["nuevo", "contactado", "en_proceso", "ganado", "perdido"] = "nuevo"
    resumen_ia: str | None = None
    estado_seguimiento: str | None = "pendiente"


class LeadUpsertResponse(BaseModel):
    id: int
    cliente_id: int


class PrivacyRequestIn(BaseModel):
    phone: str = Field(min_length=4, max_length=48)
    tipo_derecho: Literal["acceso", "rectificacion", "eliminacion", "oposicion", "portabilidad"] = "eliminacion"


class PrivacyRequestResponse(BaseModel):
    id: int


class DashboardMessagesIn(BaseModel):
    phone: str = Field(min_length=4, max_length=48)
    user_message: str = ""
    agent_message: str = ""


class DashboardMessagesResponse(BaseModel):
    message_ids: list[int]


class ExecutiveAssignIn(BaseModel):
    lead_id: int = Field(gt=0)


class ExecutiveLinkIn(BaseModel):
    lead_id: int = Field(gt=0)
    executive_id: int = Field(gt=0)


class ExecutiveOut(BaseModel):
    id: int
    nombre: str
    whatsapp: str
    leads_asignados: int | None = None


class IngestResponse(BaseModel):
    success: bool = True
    lead_id: int | None = None
    conversation_id: int | None = None
    message_id: int | None = None
    duplicate: bool = False
