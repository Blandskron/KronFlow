"""Typed AI action proposals, versioned human review, and idempotent execution (FK-17, FK-18)."""

from datetime import datetime, timedelta, timezone
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.conversation_control_service import mark_waiting_human_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.operations import Cliente, Conversation, Lead
from app.tenant_models.opportunity import Opportunity, OpportunityActivity


VALID_LEAD_STAGES = frozenset({"nuevo", "contactado", "en_proceso", "ganado", "perdido"})
ACTION_RESOURCE_MAP: dict[str, str] = {
    "crm.contact.rename": "contact",
    "crm.lead.update_stage": "lead",
    "crm.opportunity.add_note": "opportunity",
    "crm.conversation.request_handoff": "conversation",
}
DEFAULT_TTL_MINUTES = 60


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Proposal timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _canonical_hash(arguments: dict) -> str:
    raw = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def proposals_ready(db: Session, tenant: TenantContext) -> bool:
    return inspect(db.connection()).has_table(AIActionProposal.__tablename__, schema=tenant.schema_name)


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not proposals_ready(db, tenant):
        raise HTTPException(status_code=503, detail="AI proposal schema is unavailable")


def _validate_typed_arguments(action_type: str, arguments: dict) -> dict:
    if action_type not in ACTION_RESOURCE_MAP:
        raise HTTPException(status_code=422, detail=f"Unsupported AI action type: {action_type}")
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail="Proposal arguments must be a JSON object")

    if action_type == "crm.contact.rename":
        name = arguments.get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 160:
            raise HTTPException(status_code=422, detail="crm.contact.rename requires a non-empty string 'name' (<=160)")
        return {"name": name.strip()}

    if action_type == "crm.lead.update_stage":
        stage = arguments.get("stage")
        if not isinstance(stage, str) or stage.strip() not in VALID_LEAD_STAGES:
            raise HTTPException(status_code=422, detail="crm.lead.update_stage requires a valid lead 'stage'")
        return {"stage": stage.strip()}

    if action_type == "crm.opportunity.add_note":
        note = arguments.get("note")
        if not isinstance(note, str) or not note.strip() or len(note.strip()) > 2000:
            raise HTTPException(status_code=422, detail="crm.opportunity.add_note requires a non-empty string 'note'")
        return {"note": note.strip()}

    if action_type == "crm.conversation.request_handoff":
        reason = arguments.get("reason")
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 180:
            raise HTTPException(status_code=422, detail="crm.conversation.request_handoff requires a non-empty 'reason'")
        return {"reason": reason.strip()}

    raise HTTPException(status_code=422, detail="Unsupported AI action type")


def _ensure_resource_exists_in_tx(db: Session, resource_type: str, resource_id: int) -> None:
    model_map = {
        "contact": Cliente,
        "lead": Lead,
        "opportunity": Opportunity,
        "conversation": Conversation,
    }
    if db.get(model_map[resource_type], resource_id) is None:
        raise HTTPException(status_code=404, detail=f"Target {resource_type} not found")


def _proposal_to_dict(proposal: AIActionProposal, *, duplicate: bool = False) -> dict:
    return {
        "id": proposal.id,
        "action_type": proposal.action_type,
        "resource_type": proposal.resource_type,
        "resource_id": proposal.resource_id,
        "arguments": proposal.arguments_json,
        "idempotency_key": proposal.idempotency_key,
        "status": proposal.status,
        "proposal_version": proposal.proposal_version,
        "proposed_by": proposal.proposed_by,
        "rationale": proposal.rationale,
        "correlation_id": proposal.correlation_id,
        "expires_at": proposal.expires_at,
        "reviewed_by": proposal.reviewed_by,
        "reviewed_at": proposal.reviewed_at,
        "review_note": proposal.review_note,
        "executed_by": proposal.executed_by,
        "executed_at": proposal.executed_at,
        "effect_result": proposal.effect_result,
        "created_at": proposal.created_at,
        "updated_at": proposal.updated_at,
        "duplicate": duplicate,
    }


def create_ai_proposal(
    db: Session,
    tenant: TenantContext,
    *,
    action_type: str,
    resource_id: int,
    arguments: dict,
    idempotency_key: str,
    proposed_by: str,
    rationale: str | None = None,
    expires_at: datetime | None = None,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Persist a typed AI action proposal without executing any side effect."""
    clean_action = action_type.strip()
    clean_key = idempotency_key.strip()
    if not clean_key or len(clean_key) > 180:
        raise HTTPException(status_code=422, detail="idempotency_key must be 1..180 characters")
    validated_args = _validate_typed_arguments(clean_action, arguments)
    resource_type = ACTION_RESOURCE_MAP[clean_action]

    current = _now(now)
    expiry = _now(expires_at) if expires_at is not None else current + timedelta(minutes=DEFAULT_TTL_MINUTES)
    if expiry <= current:
        raise HTTPException(status_code=422, detail="expires_at must be in the future")

    digest = _canonical_hash({"resource_id": resource_id, "arguments": validated_args})
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    _ensure_resource_exists_in_tx(db, resource_type, resource_id)

    resolved_corr = correlation_id or audit_correlation.get()
    inserted_id = db.scalar(
        insert(AIActionProposal)
        .values(
            action_type=clean_action,
            resource_type=resource_type,
            resource_id=resource_id,
            arguments_json=validated_args,
            arguments_hash=digest,
            idempotency_key=clean_key,
            status="pending",
            proposal_version=1,
            proposed_by=proposed_by.strip()[:64] or "agent-core",
            rationale=rationale.strip()[:240] if rationale else None,
            correlation_id=resolved_corr,
            expires_at=expiry,
            created_at=current,
            updated_at=current,
        )
        .on_conflict_do_nothing(index_elements=["action_type", "idempotency_key"])
        .returning(AIActionProposal.id)
    )
    if inserted_id is None:
        existing = db.scalar(
            select(AIActionProposal).where(
                AIActionProposal.action_type == clean_action,
                AIActionProposal.idempotency_key == clean_key,
            )
        )
        if existing is None or existing.arguments_hash != digest:
            db.rollback()
            raise HTTPException(status_code=409, detail="Proposal idempotency key reused with different arguments")
        db.commit()
        return _proposal_to_dict(existing, duplicate=True)

    proposal = db.get(AIActionProposal, inserted_id)
    create_system_event(
        db,
        "ai.proposal.created",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "proposal_id": proposal.id,
            "action_type": clean_action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "proposed_by": proposal.proposed_by,
        },
    )
    db.commit()
    db.refresh(proposal)
    return _proposal_to_dict(proposal, duplicate=False)


def list_ai_proposals(
    db: Session,
    tenant: TenantContext,
    *,
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
) -> tuple[list[dict], int]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    stmt = select(AIActionProposal)
    if status_filter:
        stmt = stmt.where(AIActionProposal.status == status_filter)
    if resource_type:
        stmt = stmt.where(AIActionProposal.resource_type == resource_type)
    if resource_id is not None:
        stmt = stmt.where(AIActionProposal.resource_id == resource_id)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(stmt.order_by(AIActionProposal.id.desc()).offset(offset).limit(limit)).all()
    return [_proposal_to_dict(row) for row in rows], total


def get_ai_proposal(db: Session, tenant: TenantContext, proposal_id: int) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    proposal = db.get(AIActionProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="AI proposal not found")
    return _proposal_to_dict(proposal)


def review_ai_proposal(
    db: Session,
    tenant: TenantContext,
    proposal_id: int,
    *,
    decision: str,
    expected_version: int,
    reviewer_user_id: str,
    review_note: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Approve or reject a concrete proposal_version, enforcing expiration."""
    if decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    proposal = db.scalar(select(AIActionProposal).where(AIActionProposal.id == proposal_id).with_for_update())
    if proposal is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="AI proposal not found")
    if proposal.proposal_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale proposal version")
    if proposal.status != "pending":
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot review proposal in status '{proposal.status}'")
    if proposal.expires_at <= current:
        proposal.status = "expired"
        proposal.updated_at = current
        db.commit()
        raise HTTPException(status_code=409, detail="Proposal has expired")

    proposal.status = decision
    proposal.proposal_version += 1
    proposal.reviewed_by = reviewer_user_id[:64]
    proposal.reviewed_at = current
    proposal.review_note = review_note.strip()[:240] if review_note else None
    proposal.updated_at = current

    event_name = "ai.proposal.approved" if decision == "approved" else "ai.proposal.rejected"
    create_system_event(
        db,
        event_name,
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "proposal_id": proposal.id,
            "action_type": proposal.action_type,
            "proposal_version": proposal.proposal_version,
            "reviewed_by": proposal.reviewed_by,
        },
    )
    db.commit()
    db.refresh(proposal)
    return _proposal_to_dict(proposal)


def execute_ai_proposal(
    db: Session,
    tenant: TenantContext,
    proposal_id: int,
    *,
    executor_user_id: str,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> dict:
    """Execute an approved proposal at most once with live runtime check and full audit."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant.auth_tenant_id))
    if runtime is not None and runtime.status != "active":
        db.rollback()
        raise HTTPException(status_code=403, detail="Tenant runtime is not active")

    proposal = db.scalar(select(AIActionProposal).where(AIActionProposal.id == proposal_id).with_for_update())
    if proposal is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="AI proposal not found")

    # Idempotent repeat of an already-executed proposal never applies the effect a second time.
    if proposal.status == "executed":
        db.commit()
        return _proposal_to_dict(proposal, duplicate=True)

    if expected_version is not None and proposal.proposal_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale proposal version")
    if proposal.status != "approved":
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Only approved proposals can be executed, got '{proposal.status}'")
    if proposal.expires_at <= current:
        proposal.status = "expired"
        proposal.updated_at = current
        db.commit()
        raise HTTPException(status_code=409, detail="Approved proposal has expired before execution")

    effect_result = _apply_typed_effect_in_tx(db, tenant, proposal, executor_user_id=executor_user_id, now=current)

    proposal.status = "executed"
    proposal.proposal_version += 1
    proposal.executed_by = executor_user_id[:64]
    proposal.executed_at = current
    proposal.effect_result = effect_result
    proposal.updated_at = current

    create_system_event(
        db,
        "ai.proposal.executed",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "proposal_id": proposal.id,
            "action_type": proposal.action_type,
            "resource_type": proposal.resource_type,
            "resource_id": proposal.resource_id,
            "executed_by": proposal.executed_by,
            "proposal_version": proposal.proposal_version,
        },
    )
    db.commit()
    db.refresh(proposal)
    return _proposal_to_dict(proposal, duplicate=False)


def _apply_typed_effect_in_tx(
    db: Session,
    tenant: TenantContext,
    proposal: AIActionProposal,
    *,
    executor_user_id: str,
    now: datetime,
) -> dict:
    args = proposal.arguments_json or {}
    if proposal.action_type == "crm.contact.rename":
        contact = db.get(Cliente, proposal.resource_id)
        if contact is None:
            raise HTTPException(status_code=404, detail="Target contact not found")
        previous = contact.nombre
        contact.nombre = args["name"]
        return {"contact_id": contact.id, "previous_name": previous, "name": contact.nombre}

    if proposal.action_type == "crm.lead.update_stage":
        lead = db.get(Lead, proposal.resource_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Target lead not found")
        previous = lead.estado
        lead.estado = args["stage"]
        return {"lead_id": lead.id, "previous_stage": previous, "stage": lead.estado}

    if proposal.action_type == "crm.opportunity.add_note":
        opp = db.get(Opportunity, proposal.resource_id)
        if opp is None:
            raise HTTPException(status_code=404, detail="Target opportunity not found")
        activity = OpportunityActivity(
            opportunity_id=opp.id,
            activity_type="note",
            actor_user_id=executor_user_id[:64],
            note=args["note"],
            metadata_json={"proposal_id": proposal.id, "source": "ai_proposal"},
            created_at=now,
        )
        db.add(activity)
        db.flush()
        return {"opportunity_id": opp.id, "activity_id": activity.id}

    if proposal.action_type == "crm.conversation.request_handoff":
        control = mark_waiting_human_in_tx(
            db, tenant, proposal.resource_id, actor_user_id=executor_user_id, reason=args["reason"], now=now,
        )
        return {
            "conversation_id": proposal.resource_id,
            "mode": control.mode if control else "waiting_human",
            "control_version": control.control_version if control else None,
        }

    raise HTTPException(status_code=422, detail=f"Unsupported AI action type: {proposal.action_type}")
