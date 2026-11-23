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
