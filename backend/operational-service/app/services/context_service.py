"""Delegated business context, document CRUD, rules, traces, setup-chat, and conversation memory helpers."""

from datetime import datetime, timezone
import re
from typing import Any, Sequence
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.schemas.context import (
    AgentRuleCreateIn,
    AgentRulePatchIn,
    AgentTraceCreateIn,
    ContextDocumentCreate,
    ContextDocumentPatch,
)
from app.services.ai_extensions_service import list_conversation_memory
from app.services.tenant_data import bind_tenant_session
from app.tenant_models.agent_platform import AgentExecutionTrace, AgentRule, SetupChatSession
from app.tenant_models.context import BusinessContextDocument, DocumentChunk
from app.tenant_models.operations import Conversation


RECOMMENDED_CONTEXT_DOCUMENTS = 5
TOKEN_RE = re.compile(r"[a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]{3,}")
SETUP_QUESTIONS = (
    "¿Cuál es el nombre de la empresa y qué productos o servicios ofrece?",
    "¿Qué reglas de atención, tono y criterios de derivación humana debe respetar el agente?",
    "¿Cuáles son los horarios, canales oficiales y políticas comerciales clave? Puedes generar el contexto cuando quieras.",
)


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


def create_context_document(
    db: Session,
    tenant: TenantContext,
    payload: ContextDocumentCreate,
    *,
    source_type: str = "upload",
) -> dict[str, Any]:
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
        source_type=source_type[:32],
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


def get_context_document(db: Session, tenant: TenantContext, document_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    doc = db.scalar(
        select(BusinessContextDocument).where(
            BusinessContextDocument.id == document_id,
            BusinessContextDocument.tenant_id == str(tenant.auth_tenant_id),
        )
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document_to_dict(doc)


def patch_context_document(
    db: Session, tenant: TenantContext, document_id: int, payload: ContextDocumentPatch,
) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    doc = db.scalar(
        select(BusinessContextDocument)
        .where(
            BusinessContextDocument.id == document_id,
            BusinessContextDocument.tenant_id == str(tenant.auth_tenant_id),
        )
        .with_for_update()
    )
    if doc is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Document not found")
    if payload.title is not None:
        doc.title = payload.title.strip()[:220]
    if payload.status is not None:
        clean_status = payload.status.strip()
        if clean_status not in ("draft", "active", "deprecated", "archived", "rejected", "error", "processing"):
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid document status")
        doc.status = clean_status
    if payload.priority is not None:
        doc.priority = int(payload.priority)
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    return document_to_dict(doc)


def delete_context_document(db: Session, tenant: TenantContext, document_id: int) -> None:
    bind_tenant_session(db, tenant.schema_name)
    doc = db.scalar(
        select(BusinessContextDocument)
        .where(
            BusinessContextDocument.id == document_id,
            BusinessContextDocument.tenant_id == str(tenant.auth_tenant_id),
        )
        .with_for_update()
    )
    if doc is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Document not found")
    db.delete(doc)
    db.commit()


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
        "document_actions": {"delete": True, "patch": True, "replace": False, "retry_processing": False},
    }


def retrieve_context_sources(
    db: Session,
    tenant: TenantContext,
    query: str,
    limit: int = 3,
    document_ids: Sequence[int] | None = None,
) -> list[dict[str, Any]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return []
    bind_tenant_session(db, tenant.schema_name)
    stmt = (
        select(DocumentChunk, BusinessContextDocument)
        .join(BusinessContextDocument, BusinessContextDocument.id == DocumentChunk.document_id)
        .where(DocumentChunk.tenant_id == str(tenant.auth_tenant_id), BusinessContextDocument.status == "active")
    )
    if document_ids:
        cleaned_ids = [int(doc_id) for doc_id in document_ids if int(doc_id) > 0]
        if cleaned_ids:
            stmt = stmt.where(BusinessContextDocument.id.in_(cleaned_ids))
    rows = db.execute(stmt).all()
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


# --- Delegated agent rules ---

def _rule_to_dict(rule: AgentRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "tenant_id": rule.tenant_id,
        "agent_id": rule.agent_id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "content": rule.content,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def list_agent_rules(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    if not inspect(db.connection()).has_table(AgentRule.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Agent rules schema is unavailable")
    rows = db.scalars(
        select(AgentRule)
        .where(AgentRule.tenant_id == str(tenant.auth_tenant_id))
        .order_by(AgentRule.priority.asc(), AgentRule.id.asc())
    ).all()
    return [_rule_to_dict(r) for r in rows]


def create_agent_rule(db: Session, tenant: TenantContext, payload: AgentRuleCreateIn) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    if not inspect(db.connection()).has_table(AgentRule.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Agent rules schema is unavailable")
    now = datetime.now(timezone.utc)
    rule = AgentRule(
        tenant_id=str(tenant.auth_tenant_id),
        agent_id=payload.agent_id,
        name=payload.name.strip()[:160],
        rule_type=payload.rule_type.strip()[:48] or "general",
        content=payload.content.strip(),
        priority=payload.priority,
        is_active=bool(payload.is_active),
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _rule_to_dict(rule)


def patch_agent_rule(
    db: Session, tenant: TenantContext, rule_id: int, payload: AgentRulePatchIn,
) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    rule = db.scalar(
        select(AgentRule)
        .where(AgentRule.id == rule_id, AgentRule.tenant_id == str(tenant.auth_tenant_id))
        .with_for_update()
    )
    if rule is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Rule not found")
    if payload.name is not None:
        rule.name = payload.name.strip()[:160]
    if payload.content is not None:
        rule.content = payload.content.strip()
    if payload.priority is not None:
        rule.priority = payload.priority
    if payload.is_active is not None:
        rule.is_active = bool(payload.is_active)
    rule.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rule)
    return _rule_to_dict(rule)


def delete_agent_rule(db: Session, tenant: TenantContext, rule_id: int) -> None:
    bind_tenant_session(db, tenant.schema_name)
    rule = db.scalar(
        select(AgentRule)
        .where(AgentRule.id == rule_id, AgentRule.tenant_id == str(tenant.auth_tenant_id))
        .with_for_update()
    )
    if rule is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()


# --- Delegated execution traces ---

def _trace_to_dict(trace: AgentExecutionTrace) -> dict[str, Any]:
    return {
        "id": trace.id,
        "tenant_id": trace.tenant_id,
        "conversation_id": trace.conversation_id,
        "agent_id": trace.agent_id,
        "agent_revision_id": trace.agent_revision_id,
        "query": trace.query,
        "output_message": trace.output_message,
        "confidence": trace.confidence,
        "requires_human": trace.requires_human,
        "is_simulation": trace.is_simulation,
        "sources": list(trace.sources or []),
        "actions": list(trace.actions or []),
        "correlation_id": trace.correlation_id,
        "created_at": trace.created_at,
    }


def create_agent_trace(db: Session, tenant: TenantContext, payload: AgentTraceCreateIn) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    if not inspect(db.connection()).has_table(AgentExecutionTrace.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Agent traces schema is unavailable")
    trace = AgentExecutionTrace(
        tenant_id=str(tenant.auth_tenant_id),
        conversation_id=payload.conversation_id.strip()[:128],
        agent_id=payload.agent_id,
        agent_revision_id=payload.agent_revision_id,
        query=payload.query,
        output_message=payload.output_message,
        confidence=float(payload.confidence),
        requires_human=bool(payload.requires_human),
        is_simulation=bool(payload.is_simulation),
        sources=list(payload.sources or []),
        actions=list(payload.actions or []),
        correlation_id=audit_correlation.get(),
        created_at=datetime.now(timezone.utc),
    )
    db.add(trace)
    db.commit()
    db.refresh(trace)
    return _trace_to_dict(trace)


def get_agent_trace(db: Session, tenant: TenantContext, trace_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    trace = db.scalar(
        select(AgentExecutionTrace).where(
            AgentExecutionTrace.id == trace_id,
            AgentExecutionTrace.tenant_id == str(tenant.auth_tenant_id),
        )
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return _trace_to_dict(trace)


def list_conversation_traces(db: Session, tenant: TenantContext, conversation_id: str) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    rows = db.scalars(
        select(AgentExecutionTrace)
        .where(
            AgentExecutionTrace.tenant_id == str(tenant.auth_tenant_id),
            AgentExecutionTrace.conversation_id == conversation_id.strip()[:128],
        )
        .order_by(AgentExecutionTrace.id.asc())
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Conversation traces not found")
    return [_trace_to_dict(r) for r in rows]


# --- Persistent setup-chat sessions ---

def create_setup_session(db: Session, tenant: TenantContext, *, objective: str = "build_business_context") -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    if not inspect(db.connection()).has_table(SetupChatSession.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Setup chat schema is unavailable")
    session_id = f"{tenant.auth_tenant_id}-{uuid4().hex[:16]}"
    now = datetime.now(timezone.utc)
    row = SetupChatSession(
        id=session_id,
        tenant_id=str(tenant.auth_tenant_id),
        objective=objective.strip()[:120] or "build_business_context",
        status="draft",
        messages=[],
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return {"session_id": session_id, "next_question": SETUP_QUESTIONS[0]}


def append_setup_message(
    db: Session, tenant: TenantContext, session_id: str, *, content: str,
) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    row = db.scalar(
        select(SetupChatSession)
        .where(
            SetupChatSession.id == session_id,
            SetupChatSession.tenant_id == str(tenant.auth_tenant_id),
        )
        .with_for_update()
    )
    if row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Setup session not found")
    messages = list(row.messages or [])
    messages.append({"role": "user", "content": content.strip(), "at": datetime.now(timezone.utc).isoformat()})
    row.messages = messages
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    next_idx = min(len(messages), len(SETUP_QUESTIONS) - 1)
    return {"session_id": row.id, "next_question": SETUP_QUESTIONS[next_idx]}


def generate_setup_context(db: Session, tenant: TenantContext, session_id: str) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    row = db.scalar(
        select(SetupChatSession)
        .where(
            SetupChatSession.id == session_id,
            SetupChatSession.tenant_id == str(tenant.auth_tenant_id),
        )
        .with_for_update()
    )
    if row is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Setup session not found")
    user_entries = [m.get("content", "").strip() for m in (row.messages or []) if m.get("content")]
    if user_entries:
        summary = "Resumen de configuración empresarial:\n\n" + "\n".join(f"- {entry}" for entry in user_entries)
    else:
        summary = f"Contexto estructurado pendiente de revisión humana para tenant {tenant.auth_tenant_id}."

    filename = f"setup-chat-{row.id[:24]}.md"
    tenant_id = str(tenant.auth_tenant_id)
    next_version = int(
        db.scalar(
            select(func.coalesce(func.max(BusinessContextDocument.version), 0)).where(
                BusinessContextDocument.tenant_id == tenant_id,
                BusinessContextDocument.filename == filename,
            )
        )
        or 0
    ) + 1
    doc = BusinessContextDocument(
        tenant_id=tenant_id,
        title="Contexto generado por asistente",
        filename=filename,
        content_type="text/markdown",
        status="draft",
        priority=100,
        version=next_version,
        source_type="setup_chat",
        raw_text=summary,
    )
    db.add(doc)
    db.flush()
    db.add(
        DocumentChunk(
            tenant_id=tenant_id,
            document_id=doc.id,
            chunk_index=0,
            content=summary,
            token_count=len(summary.split()),
            source_ref=f"{filename}#0",
        )
    )
    row.status = "generated"
    row.generated_summary = summary
    row.generated_document_id = doc.id
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"summary": summary, "status": "draft", "document_id": doc.id}


def list_conversation_memory_by_ref(
    db: Session,
    tenant: TenantContext,
    conversation_ref: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Lookup active conversation memory by numeric conversation ID or external session_id."""
    bind_tenant_session(db, tenant.schema_name)
    conv: Conversation | None = None
    if conversation_ref.isdigit():
        conv = db.get(Conversation, int(conversation_ref))
    if conv is None:
        conv = db.scalar(select(Conversation).where(Conversation.session_id == conversation_ref))
    if conv is None:
        return []
    return list_conversation_memory(db, tenant, conv.id, limit=limit)
