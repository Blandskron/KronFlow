"""Specialist multi-agent handoff with bounded hop limits and automatic HITL fallback."""

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.conversation import AgentHandoffIn
from app.services.conversation_control_service import mark_waiting_human_in_tx
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.agent_platform import AgentExecutionTrace
from app.tenant_models.context import TenantAgentProfile
from app.tenant_models.operations import Conversation


HANDOFF_MARKER = "[agent_handoff]"


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Agent handoff timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _require_handoff_ready(db: Session, tenant: TenantContext) -> None:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    if not {TenantAgentProfile.__tablename__, AgentExecutionTrace.__tablename__}.issubset(existing):
        raise HTTPException(status_code=503, detail="Agent platform schema is unavailable")


def handoff_conversation_to_agent(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
    payload: AgentHandoffIn,
    *,
    actor_user_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_handoff_ready(db, tenant)

    conv = db.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    target = db.get(TenantAgentProfile, payload.target_agent_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target specialist agent not found")
    if target.status != "active" or target.active_revision_id is None:
        raise HTTPException(status_code=422, detail="Target specialist agent must be active with a published revision")

    prior_hops = int(
        db.scalar(
            select(func.count())
            .select_from(AgentExecutionTrace)
            .where(
                AgentExecutionTrace.tenant_id == str(tenant.auth_tenant_id),
                AgentExecutionTrace.conversation_id == str(conversation_id),
                AgentExecutionTrace.query == HANDOFF_MARKER,
            )
        )
        or 0
    )

    if prior_hops >= payload.max_hops:
        mark_waiting_human_in_tx(
            db,
            tenant,
            conversation_id,
            actor_user_id=actor_user_id,
            reason="agent_handoff_hop_limit_exceeded",
            now=current,
        )
        create_system_event(
            db,
            "agent.handoff.hop_limit_escalated",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {
                "conversation_id": conversation_id,
                "prior_hops": prior_hops,
                "max_hops": payload.max_hops,
                "target_agent_id": target.id,
            },
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="Specialist agent handoff hop limit exceeded; escalated to human review",
        )

    hop_number = prior_hops + 1
    clean_reason = payload.reason.strip()[:240]
    clean_summary = payload.shared_summary.strip()[:1000]
    meta_action = {
        "type": "agent_handoff",
        "from_agent_id": payload.from_agent_id,
        "to_agent_id": target.id,
        "to_agent_revision_id": int(target.active_revision_id),
        "reason": clean_reason,
        "shared_summary": clean_summary,
        "hop_number": hop_number,
        "actor_user_id": actor_user_id,
    }
    trace = AgentExecutionTrace(
        tenant_id=str(tenant.auth_tenant_id),
        conversation_id=str(conversation_id),
        agent_id=target.id,
        agent_revision_id=int(target.active_revision_id),
        query=HANDOFF_MARKER,
        output_message=clean_summary or clean_reason,
        confidence=1.0,
        requires_human=False,
        is_simulation=False,
        sources=[],
        actions=[meta_action],
        created_at=current,
    )
    db.add(trace)
    db.flush()

    event_payload = {
        "conversation_id": conversation_id,
        "from_agent_id": payload.from_agent_id,
        "to_agent_id": target.id,
        "to_agent_revision_id": int(target.active_revision_id),
        "hop_number": hop_number,
        "reason": clean_reason,
    }
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="agent.handoff.completed",
        aggregate_type="conversation",
        aggregate_id=conversation_id,
        payload=event_payload,
        occurred_at=current,
    )
    create_system_event(db, "agent.handoff.completed", tenant.auth_tenant_id, tenant.schema_name, event_payload)
    db.commit()
    db.refresh(trace)

    return {
        "trace_id": trace.id,
        "conversation_id": conversation_id,
        "from_agent_id": payload.from_agent_id,
        "to_agent_id": target.id,
        "to_agent_revision_id": int(target.active_revision_id),
        "hop_number": hop_number,
        "max_hops": payload.max_hops,
        "reason": clean_reason,
        "shared_summary": clean_summary,
        "actor_user_id": actor_user_id,
        "created_at": trace.created_at,
    }


def list_conversation_agent_handoffs(
    db: Session,
    tenant: TenantContext,
    conversation_id: int,
) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_handoff_ready(db, tenant)
    if db.get(Conversation, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    traces = list(
        db.scalars(
            select(AgentExecutionTrace)
            .where(
                AgentExecutionTrace.tenant_id == str(tenant.auth_tenant_id),
                AgentExecutionTrace.conversation_id == str(conversation_id),
                AgentExecutionTrace.query == HANDOFF_MARKER,
            )
            .order_by(AgentExecutionTrace.id.asc())
        ).all()
    )
    items: list[dict[str, Any]] = []
    for idx, trace in enumerate(traces, start=1):
        meta = dict((trace.actions or [{}])[0]) if trace.actions else {}
        items.append(
            {
                "trace_id": trace.id,
                "conversation_id": conversation_id,
                "from_agent_id": meta.get("from_agent_id"),
                "to_agent_id": meta.get("to_agent_id", trace.agent_id),
                "to_agent_revision_id": meta.get("to_agent_revision_id", trace.agent_revision_id),
                "hop_number": int(meta.get("hop_number") or idx),
                "reason": str(meta.get("reason") or trace.output_message),
                "shared_summary": str(meta.get("shared_summary") or trace.output_message),
                "actor_user_id": meta.get("actor_user_id"),
                "created_at": trace.created_at,
            }
        )
    return items
