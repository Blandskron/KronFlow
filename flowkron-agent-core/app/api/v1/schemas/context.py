from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str
    filename: str
    content: str
    content_type: str = "text/plain"
    status: str = "active"
    priority: int = 100


class DocumentPatch(BaseModel):
    title: str | None = None
    status: str | None = None
    priority: int | None = None


class DocumentRead(BaseModel):
    id: int
    tenant_id: str
    title: str
    filename: str
    content_type: str | None = None
    status: str
    priority: int
    version: int
    source_type: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class BusinessContextStatusRead(BaseModel):
    progress_percent: int
    agent_status: str
    last_updated_at: str | None
    active_documents_count: int
    documents: list[DocumentRead]
    document_actions: dict[str, bool] = Field(default_factory=dict)


class FieldRead(BaseModel):
    id: int
    name: str
    label: str
    field_type: str
    required: bool
    position: int

    model_config = {"from_attributes": True}


class FormRead(BaseModel):
    id: int
    code: str
    name: str
    description: str
    fields: list[FieldRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class FormSubmissionCreate(BaseModel):
    payload: dict[str, Any]


class FormSubmissionRead(BaseModel):
    id: int
    tenant_id: str
    form_id: int
    payload: dict[str, Any]

    model_config = {"from_attributes": True}


class TemplateDownloadOptionRead(BaseModel):
    format: str
    template_id: int
    filename: str
    media_type: str


class TemplateRead(BaseModel):
    id: int
    code: str
    name: str
    description: str
    fields: list[dict[str, Any]]
    download_options: list[TemplateDownloadOptionRead]

    model_config = {"from_attributes": True}
