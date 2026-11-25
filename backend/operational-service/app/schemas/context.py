from datetime import datetime

from pydantic import BaseModel, Field


class ContextChunkCreate(BaseModel):
    chunk_index: int
    content: str
    token_count: int
    source_ref: str = ""


class ContextDocumentCreate(BaseModel):
    tenant_id: str
    title: str
    filename: str
    content_type: str = "text/plain"
    status: str = "active"
    priority: int = 100
    raw_text: str
    chunks: list[ContextChunkCreate] = Field(default_factory=list)


class ContextDocumentRead(BaseModel):
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
    documents: list[ContextDocumentRead]
    document_actions: dict[str, bool] = Field(default_factory=dict)


class ContextRetrieveRequest(BaseModel):
    query: str
    limit: int = 3


class ContextSourceRead(BaseModel):
    document_id: int
    chunk_id: int
    title: str
    score: float
    content: str
