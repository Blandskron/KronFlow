import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.context import ContextDocumentCreate
from app.services.tenant_data import bind_tenant_session
from app.tenant_models.context import BusinessContextDocument, DocumentChunk


RECOMMENDED_CONTEXT_DOCUMENTS = 5
TOKEN_RE = re.compile(r"[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]{3,}")


def document_to_dict(document: BusinessContextDocument) -> dict[str, Any]:
    return {
        "id": document.id,
        "tenant_id": document.tenant_id,
        "title": document.title,
        "filename": document.filename,
        "content_type": document.content_type,
        "status": document.status,
        "priority": document.priority,
        "version": document.version,
        "source_type": document.source_type,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "error_message": None,
    }


def create_context_document(db: Session, tenant: TenantContext, payload: ContextDocumentCreate) -> dict[str, Any]:
    if payload.tenant_id and payload.tenant_id != str(tenant.auth_tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Payload tenant does not match resolved runtime")
    bind_tenant_session(db, tenant.schema_name)
    tenant_id = str(tenant.auth_tenant_id)
    next_version = int(
        db.scalar(
            select(func.coalesce(func.max(BusinessContextDocument.version), 0)).where(
                BusinessContextDocument.tenant_id == tenant_id,
                BusinessContextDocument.filename == payload.filename,
            )
        )
        or 0
    ) + 1
    document = BusinessContextDocument(
        tenant_id=tenant_id,
        title=payload.title,
        filename=payload.filename,
        content_type=payload.content_type,
        status=payload.status,
        priority=payload.priority,
        version=next_version,
        raw_text=payload.raw_text,
    )
    db.add(document)
    db.flush()
    for chunk in payload.chunks:
        db.add(
            DocumentChunk(
                tenant_id=tenant_id,
                document_id=document.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                token_count=chunk.token_count,
                source_ref=chunk.source_ref,
            )
        )
    db.commit()
    db.refresh(document)
    return document_to_dict(document)


def list_context_documents(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    documents = db.scalars(
        select(BusinessContextDocument)
        .where(BusinessContextDocument.tenant_id == str(tenant.auth_tenant_id))
        .order_by(BusinessContextDocument.id)
    ).all()
    return [document_to_dict(document) for document in documents]


def context_status(db: Session, tenant: TenantContext) -> dict[str, Any]:
    documents = list_context_documents(db, tenant)
    active_documents = [document for document in documents if document["status"] == "active"]
    active_count = len(active_documents)
    progress_percent = min(round((active_count / RECOMMENDED_CONTEXT_DOCUMENTS) * 100), 100) if active_count else 0
    timestamps = [
        value.isoformat()
        for document in documents
        for value in (document.get("updated_at"), document.get("created_at"))
        if value
    ]
    if not documents:
        agent_status = "not_configured"
    elif any(document["status"] in {"rejected", "error"} for document in documents):
        agent_status = "error"
    elif active_count >= RECOMMENDED_CONTEXT_DOCUMENTS:
        agent_status = "trained"
    elif active_count > 0:
        agent_status = "pending"
    else:
        agent_status = "processing"
    return {
        "progress_percent": progress_percent,
        "agent_status": agent_status,
        "last_updated_at": max(timestamps) if timestamps else None,
        "active_documents_count": active_count,
        "documents": documents,
        "document_actions": {"delete": False, "patch": False, "replace": False, "retry_processing": False},
    }


def retrieve_context_sources(db: Session, tenant: TenantContext, query: str, limit: int = 3) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    bind_tenant_session(db, tenant.schema_name)
    rows = db.execute(
        select(DocumentChunk, BusinessContextDocument)
        .join(BusinessContextDocument, BusinessContextDocument.id == DocumentChunk.document_id)
        .where(DocumentChunk.tenant_id == str(tenant.auth_tenant_id), BusinessContextDocument.status == "active")
    ).all()
    ranked: list[dict[str, Any]] = []
    for chunk, document in rows:
        content_tokens = _tokens(chunk.content)
        if not content_tokens:
            continue
        overlap = len(query_tokens.intersection(content_tokens))
        score = overlap / max(len(query_tokens), 1)
        if score > 0:
            ranked.append(
                {
                    "document_id": document.id,
                    "chunk_id": chunk.id,
                    "title": document.title,
                    "score": min(score, 1.0),
                    "content": chunk.content,
                }
            )
    return sorted(ranked, key=lambda source: source["score"], reverse=True)[: max(min(limit, 10), 1)]


def _tokens(value: str) -> set[str]:
    return {match.group(0).lower() for match in TOKEN_RE.finditer(value)}
