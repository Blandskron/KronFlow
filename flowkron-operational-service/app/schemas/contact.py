from datetime import datetime

from pydantic import BaseModel


class ContactOut(BaseModel):
    id: int
    full_name: str
    email: str | None
    phone: str | None
    source: str
    created_at: datetime


class ContactListResponse(BaseModel):
    items: list[ContactOut]
    total: int
    limit: int
    offset: int
