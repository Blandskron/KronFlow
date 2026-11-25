from datetime import datetime

from pydantic import BaseModel


class AuditDomainEvent(BaseModel):
    event_id: str
    event_type: str
    event_version: str = "v1"
    occurred_at: datetime
    producer: str = "operational-service"
    tenant_id: str
    correlation_id: str
    trace_id: str | None = None
    data: dict[str, str | int]


class AuditEventPage(BaseModel):
    items: list[AuditDomainEvent]
    next_before_id: int | None
