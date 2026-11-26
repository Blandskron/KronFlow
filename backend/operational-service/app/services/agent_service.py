"""Multi-agent catalog with editable drafts, immutable revisions, publication checks, and rollback."""

from datetime import datetime, timezone
from typing import Sequence

from fastapi import HTTPException
from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.agent import AgentConfigureRequest, AgentUpdateRequest
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.agent_platform import AgentRevision
from app.tenant_models.context import BusinessContextDocument, TenantAgentProfile


ALLOWED_AGENT_TOOLS = frozenset(
    {
        "handoff_human",
        "crm.contact.rename",
        "crm.lead.update_stage",
        "crm.opportunity.add_note",
        "crm.conversation.request_handoff",
    }
)


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Agent timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    if not (
        inspector.has_table(TenantAgentProfile.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(AgentRevision.__tablename__, schema=tenant.schema_name)
    ):
        raise HTTPException(status_code=503, detail="Agent catalog schema is unavailable")


def _validate_tools(tools: Sequence[str]) -> list[str]:
    cleaned = sorted({t.strip() for t in tools if t and t.strip()})
    unsupported = sorted(set(cleaned) - ALLOWED_AGENT_TOOLS)
    if unsupported:
        raise HTTPException(status_code=422, detail=f"Unsupported agent tools: {', '.join(unsupported)}")
    return cleaned


def _validate_documents(
    db: Session,
    tenant: TenantContext,
    doc_ids: Sequence[int],
    *,
    require_active: bool,
) -> list[int]:
    cleaned = sorted({int(doc_id) for doc_id in doc_ids if int(doc_id) > 0})
    if not cleaned:
        return []
    tenant_id = str(tenant.auth_tenant_id)
    rows = list(
        db.scalars(
            select(BusinessContextDocument).where(
                BusinessContextDocument.tenant_id == tenant_id,
                BusinessContextDocument.id.in_(cleaned),
            )
        ).all()
    )
    by_id = {row.id: row for row in rows}
    missing = [doc_id for doc_id in cleaned if doc_id not in by_id]
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown document IDs for tenant: {missing}")
    if require_active:
        inactive = [doc_id for doc_id in cleaned if by_id[doc_id].status != "active"]
        if inactive:
            raise HTTPException(status_code=422, detail=f"Referenced documents are not active: {inactive}")
    return cleaned


def _revision_to_dict(rev: AgentRevision) -> dict:
    return {
        "id": rev.id,
        "agent_id": rev.agent_id,
        "revision_number": rev.revision_number,
        "status": rev.status,
        "name": rev.name,
        "role": rev.role,
        "tone": rev.tone,
        "language": rev.language,
        "instructions": rev.instructions,
        "allowed_tools": list(rev.allowed_tools or []),
        "allowed_document_ids": [int(x) for x in (rev.allowed_document_ids or [])],
        "limits": dict(rev.limits_json or {}),
        "prompt_config": dict(rev.prompt_config or {}),
        "publish_note": rev.publish_note,
        "published_by": rev.published_by,
        "published_at": rev.published_at,
    }


def _agent_to_dict(db: Session, agent: TenantAgentProfile) -> dict:
    active_rev_num = None
    if agent.active_revision_id is not None:
        active_rev = db.get(AgentRevision, agent.active_revision_id)
        if active_rev is not None:
            active_rev_num = active_rev.revision_number
    return {
        "id": agent.id,
        "name": agent.name,
        "role": agent.role,
        "status": agent.status,
        "tone": agent.tone,
        "language": agent.language,
        "instructions": agent.context_summary,
        "allowed_tools": list(agent.allowed_tools or []),
        "allowed_document_ids": [int(x) for x in (agent.allowed_document_ids or [])],
        "limits": dict(agent.limits_json or {}),
        "prompt_config": dict(agent.configuration or {}),
        "is_default": bool(agent.is_default),
        "version": agent.version,
        "active_revision_id": agent.active_revision_id,
        "active_revision_number": active_rev_num,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
    }


def list_agents(db: Session, tenant: TenantContext) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    rows = list(
        db.scalars(
            select(TenantAgentProfile)
            .where(TenantAgentProfile.tenant_id == str(tenant.auth_tenant_id))
            .order_by(TenantAgentProfile.is_default.desc(), TenantAgentProfile.id.asc())
        ).all()
    )
    return [_agent_to_dict(db, row) for row in rows]


def get_agent(db: Session, tenant: TenantContext, agent_id: int) -> dict | None:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    agent = db.scalar(
        select(TenantAgentProfile).where(
            TenantAgentProfile.id == agent_id,
            TenantAgentProfile.tenant_id == str(tenant.auth_tenant_id),
        )
    )
    if agent is None:
        return None
    return _agent_to_dict(db, agent)


def configure_agent(
    db: Session,
    tenant: TenantContext,
    payload: AgentConfigureRequest,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    tenant_id = str(tenant.auth_tenant_id)

    tools = _validate_tools(payload.allowed_tools)
    doc_ids = _validate_documents(db, tenant, payload.allowed_document_ids, require_active=False)

    has_default = db.scalar(
        select(TenantAgentProfile.id)
        .where(TenantAgentProfile.tenant_id == tenant_id, TenantAgentProfile.is_default.is_(True))
        .limit(1)
    )
    make_default = True if (payload.is_default is True or has_default is None) else False
    if make_default and has_default is not None:
        db.execute(
            update(TenantAgentProfile)
            .where(TenantAgentProfile.tenant_id == tenant_id, TenantAgentProfile.is_default.is_(True))
            .values(is_default=False, updated_at=current)
        )

    agent = TenantAgentProfile(
        tenant_id=tenant_id,
        name=payload.name.strip()[:160],
        role=payload.role.strip()[:160],
        tone=payload.tone.strip()[:120],
        language=payload.language.strip()[:16],
        status="draft",
        is_default=make_default,
        version=1,
        active_revision_id=None,
        context_summary=payload.instructions.strip(),
        allowed_tools=tools,
        allowed_document_ids=doc_ids,
        limits_json=dict(payload.limits or {}),
        configuration=dict(payload.prompt_config or {}),
        created_at=current,
        updated_at=current,
    )
    db.add(agent)
    db.flush()
    create_system_event(
        db,
        "agent.configured",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"agent_id": agent.id, "is_default": make_default, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(db, agent)


def update_agent(
    db: Session,
    tenant: TenantContext,
    agent_id: int,
    payload: AgentUpdateRequest,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict | None:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    tenant_id = str(tenant.auth_tenant_id)

    agent = db.scalar(
        select(TenantAgentProfile)
        .where(TenantAgentProfile.id == agent_id, TenantAgentProfile.tenant_id == tenant_id)
        .with_for_update()
    )
    if agent is None:
        db.rollback()
        return None
    if payload.expected_version is not None and agent.version != payload.expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale agent version")

    if payload.name is not None:
        agent.name = payload.name.strip()[:160]
    if payload.role is not None:
        agent.role = payload.role.strip()[:160]
    if payload.status is not None:
        agent.status = payload.status
    if payload.tone is not None:
        agent.tone = payload.tone.strip()[:120]
    if payload.language is not None:
        agent.language = payload.language.strip()[:16]
    if payload.instructions is not None:
        agent.context_summary = payload.instructions.strip()
    if payload.allowed_tools is not None:
        agent.allowed_tools = _validate_tools(payload.allowed_tools)
    if payload.allowed_document_ids is not None:
        agent.allowed_document_ids = _validate_documents(db, tenant, payload.allowed_document_ids, require_active=False)
    if payload.limits is not None:
        agent.limits_json = dict(payload.limits)
    if payload.prompt_config is not None:
        agent.configuration = dict(payload.prompt_config)
    if payload.is_default is True and not agent.is_default:
        db.execute(
            update(TenantAgentProfile)
            .where(
                TenantAgentProfile.tenant_id == tenant_id,
                TenantAgentProfile.is_default.is_(True),
                TenantAgentProfile.id != agent.id,
            )
            .values(is_default=False, updated_at=current)
        )
        agent.is_default = True
    elif payload.is_default is False and agent.is_default:
        other_default = db.scalar(
            select(TenantAgentProfile.id)
            .where(
                TenantAgentProfile.tenant_id == tenant_id,
                TenantAgentProfile.is_default.is_(True),
                TenantAgentProfile.id != agent.id,
            )
            .limit(1)
        )
        if other_default is None:
            db.rollback()
            raise HTTPException(status_code=409, detail="Tenant must keep at least one default agent")
        agent.is_default = False

    agent.version += 1
    agent.updated_at = current
    create_system_event(
        db,
        "agent.updated",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"agent_id": agent.id, "version": agent.version, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(db, agent)


def publish_agent(
    db: Session,
    tenant: TenantContext,
    agent_id: int,
    *,
    expected_version: int,
    actor_user_id: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    tenant_id = str(tenant.auth_tenant_id)

    agent = db.scalar(
        select(TenantAgentProfile)
        .where(TenantAgentProfile.id == agent_id, TenantAgentProfile.tenant_id == tenant_id)
        .with_for_update()
    )
    if agent is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale agent version")

    tools = _validate_tools(agent.allowed_tools or [])
    doc_ids = _validate_documents(db, tenant, agent.allowed_document_ids or [], require_active=True)

    max_rev = int(
        db.scalar(
            select(func.coalesce(func.max(AgentRevision.revision_number), 0)).where(AgentRevision.agent_id == agent.id)
        )
        or 0
    )
    db.execute(
        update(AgentRevision)
        .where(AgentRevision.agent_id == agent.id, AgentRevision.status == "active")
        .values(status="superseded")
    )

    rev = AgentRevision(
        agent_id=agent.id,
        revision_number=max_rev + 1,
        status="active",
        name=agent.name,
        role=agent.role,
        tone=agent.tone,
        language=agent.language,
        instructions=agent.context_summary,
        allowed_tools=tools,
        allowed_document_ids=doc_ids,
        limits_json=dict(agent.limits_json or {}),
        prompt_config=dict(agent.configuration or {}),
        publish_note=note.strip()[:240] if note and note.strip() else None,
        published_by=actor_user_id[:64] if actor_user_id else None,
        published_at=current,
    )
    db.add(rev)
    db.flush()

    agent.active_revision_id = rev.id
    agent.status = "active"
    agent.version += 1
    agent.updated_at = current

    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="agent.published",
        aggregate_type="agent",
        aggregate_id=agent.id,
        payload={"agent_id": agent.id, "revision_id": rev.id, "revision_number": rev.revision_number},
        occurred_at=current,
    )
    create_system_event(
        db,
        "agent.published",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"agent_id": agent.id, "revision_id": rev.id, "revision_number": rev.revision_number, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(rev)
    return _revision_to_dict(rev)


def list_agent_revisions(db: Session, tenant: TenantContext, agent_id: int) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    agent = db.scalar(
        select(TenantAgentProfile).where(
            TenantAgentProfile.id == agent_id,
            TenantAgentProfile.tenant_id == str(tenant.auth_tenant_id),
        )
    )
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    rows = list(
        db.scalars(
            select(AgentRevision)
            .where(AgentRevision.agent_id == agent.id)
            .order_by(AgentRevision.revision_number.desc())
        ).all()
    )
    return [_revision_to_dict(row) for row in rows]


def rollback_agent(
    db: Session,
    tenant: TenantContext,
    agent_id: int,
    *,
    expected_version: int,
    revision_id: int,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    tenant_id = str(tenant.auth_tenant_id)

    agent = db.scalar(
        select(TenantAgentProfile)
        .where(TenantAgentProfile.id == agent_id, TenantAgentProfile.tenant_id == tenant_id)
        .with_for_update()
    )
    if agent is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale agent version")

    target = db.scalar(
        select(AgentRevision).where(AgentRevision.id == revision_id, AgentRevision.agent_id == agent.id).with_for_update()
    )
    if target is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Agent revision not found")

    _validate_tools(target.allowed_tools or [])
    _validate_documents(db, tenant, target.allowed_document_ids or [], require_active=True)

    db.execute(
        update(AgentRevision)
        .where(AgentRevision.agent_id == agent.id, AgentRevision.status == "active", AgentRevision.id != target.id)
        .values(status="superseded")
    )
    target.status = "active"

    agent.name = target.name
    agent.role = target.role
    agent.tone = target.tone
    agent.language = target.language
    agent.context_summary = target.instructions
    agent.allowed_tools = list(target.allowed_tools or [])
    agent.allowed_document_ids = [int(x) for x in (target.allowed_document_ids or [])]
    agent.limits_json = dict(target.limits_json or {})
    agent.configuration = dict(target.prompt_config or {})
    agent.active_revision_id = target.id
    agent.status = "active"
    agent.version += 1
    agent.updated_at = current

    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="agent.rolled_back",
        aggregate_type="agent",
        aggregate_id=agent.id,
        payload={"agent_id": agent.id, "revision_id": target.id, "revision_number": target.revision_number},
        occurred_at=current,
    )
    create_system_event(
        db,
        "agent.rolled_back",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"agent_id": agent.id, "revision_id": target.id, "revision_number": target.revision_number, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(agent)
    return _agent_to_dict(db, agent)


def resolve_runtime_agent(
    db: Session,
    tenant: TenantContext,
    *,
    agent_id: int | None = None,
    agent_revision_id: int | None = None,
) -> dict | None:
    """Resolve the active immutable agent revision for inference (or None when no published agent exists)."""
    bind_tenant_session(db, tenant.schema_name)
    inspector = inspect(db.connection())
    if not (
        inspector.has_table(TenantAgentProfile.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(AgentRevision.__tablename__, schema=tenant.schema_name)
    ):
        return None
    tenant_id = str(tenant.auth_tenant_id)

    if agent_revision_id is not None:
        rev = db.get(AgentRevision, agent_revision_id)
        if rev is None:
            raise HTTPException(status_code=404, detail="Agent revision not found")
        agent = db.scalar(
            select(TenantAgentProfile).where(
                TenantAgentProfile.id == rev.agent_id,
                TenantAgentProfile.tenant_id == tenant_id,
            )
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return {
            "agent_id": agent.id,
            "agent_revision_id": rev.id,
            "revision_number": rev.revision_number,
            "name": rev.name,
            "role": rev.role,
            "tone": rev.tone,
            "language": rev.language,
            "instructions": rev.instructions,
            "allowed_tools": list(rev.allowed_tools or []),
            "allowed_document_ids": [int(x) for x in (rev.allowed_document_ids or [])],
            "limits": dict(rev.limits_json or {}),
        }

    if agent_id is not None:
        agent = db.scalar(
            select(TenantAgentProfile).where(
                TenantAgentProfile.id == agent_id,
                TenantAgentProfile.tenant_id == tenant_id,
            )
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.active_revision_id is None:
            return None
        rev = db.get(AgentRevision, agent.active_revision_id)
        if rev is None:
            return None
        return {
            "agent_id": agent.id,
            "agent_revision_id": rev.id,
            "revision_number": rev.revision_number,
            "name": rev.name,
            "role": rev.role,
            "tone": rev.tone,
            "language": rev.language,
            "instructions": rev.instructions,
            "allowed_tools": list(rev.allowed_tools or []),
            "allowed_document_ids": [int(x) for x in (rev.allowed_document_ids or [])],
            "limits": dict(rev.limits_json or {}),
        }

    agent = db.scalar(
        select(TenantAgentProfile)
        .where(
            TenantAgentProfile.tenant_id == tenant_id,
            TenantAgentProfile.active_revision_id.is_not(None),
        )
        .order_by(TenantAgentProfile.is_default.desc(), TenantAgentProfile.id.asc())
        .limit(1)
    )
    if agent is None or agent.active_revision_id is None:
        return None
    rev = db.get(AgentRevision, agent.active_revision_id)
    if rev is None:
        return None
    return {
        "agent_id": agent.id,
        "agent_revision_id": rev.id,
        "revision_number": rev.revision_number,
        "name": rev.name,
        "role": rev.role,
        "tone": rev.tone,
        "language": rev.language,
        "instructions": rev.instructions,
        "allowed_tools": list(rev.allowed_tools or []),
        "allowed_document_ids": [int(x) for x in (rev.allowed_document_ids or [])],
        "limits": dict(rev.limits_json or {}),
    }
