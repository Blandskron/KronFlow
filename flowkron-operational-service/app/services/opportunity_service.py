"""Commercial pipeline and opportunity lifecycle service (FK-29)."""

from datetime import datetime, timezone
from decimal import Decimal
import re

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente, Conversation, Lead
from app.tenant_models.opportunity import Opportunity, OpportunityActivity, PipelineStage


DEFAULT_STAGES: tuple[tuple[str, str, int, str], ...] = (
    ("qualification", "Calificación", 10, "open"),
    ("proposal", "Propuesta", 20, "open"),
    ("negotiation", "Negociación", 30, "open"),
    ("won", "Ganada", 90, "won"),
    ("lost", "Perdida", 100, "lost"),
)
ISO_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,47}$")
_UNSET = object()


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Opportunity timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def opportunities_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    return (
        inspector.has_table(PipelineStage.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(Opportunity.__tablename__, schema=tenant.schema_name)
        and inspector.has_table(OpportunityActivity.__tablename__, schema=tenant.schema_name)
    )


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not opportunities_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Opportunity pipeline schema is unavailable")


def _ensure_default_stages_in_tx(db: Session, now: datetime) -> None:
    has_any = db.scalar(select(PipelineStage.id).limit(1))
    if has_any is not None:
        return
    for slug, name, position, kind in DEFAULT_STAGES:
        db.execute(
            insert(PipelineStage)
            .values(slug=slug, name=name, position=position, stage_kind=kind, is_active=True, created_at=now)
            .on_conflict_do_nothing(index_elements=["slug"])
        )


def _normalize_currency(currency: str) -> str:
    code = currency.strip().upper()
    if not ISO_CURRENCY_RE.fullmatch(code):
        raise HTTPException(status_code=422, detail="Currency must be a 3-letter ISO 4217 code")
    return code


def _stage_to_dict(stage: PipelineStage) -> dict:
    return {
        "id": stage.id,
        "slug": stage.slug,
        "name": stage.name,
        "position": stage.position,
        "stage_kind": stage.stage_kind,
        "is_active": stage.is_active,
        "created_at": stage.created_at,
    }


def _activity_to_dict(activity: OpportunityActivity) -> dict:
    return {
        "id": activity.id,
        "opportunity_id": activity.opportunity_id,
        "activity_type": activity.activity_type,
        "actor_user_id": activity.actor_user_id,
        "from_stage_id": activity.from_stage_id,
        "to_stage_id": activity.to_stage_id,
        "note": activity.note,
        "metadata": activity.metadata_json or {},
        "created_at": activity.created_at,
    }


def _opportunity_to_dict(
    opp: Opportunity,
    stage: PipelineStage,
    activities: list[OpportunityActivity] | None = None,
) -> dict:
    data = {
        "id": opp.id,
        "contact_id": opp.contact_id,
        "lead_id": opp.lead_id,
        "conversation_id": opp.conversation_id,
        "stage_id": opp.stage_id,
        "stage_slug": stage.slug,
        "stage_name": stage.name,
        "stage_kind": stage.stage_kind,
        "title": opp.title,
        "owner_user_id": opp.owner_user_id,
        "amount": opp.amount,
        "currency": opp.currency,
        "outcome": opp.outcome,
        "close_reason": opp.close_reason,
        "version": opp.version,
        "closed_at": opp.closed_at,
        "created_at": opp.created_at,
        "updated_at": opp.updated_at,
    }
    if activities is not None:
        data["activities"] = [_activity_to_dict(item) for item in activities]
    return data


def list_pipeline_stages(db: Session, tenant: TenantContext) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    _ensure_default_stages_in_tx(db, _now())
    db.commit()
    stages = db.scalars(
        select(PipelineStage).order_by(PipelineStage.position.asc(), PipelineStage.id.asc())
    ).all()
    return [_stage_to_dict(stage) for stage in stages]


def create_pipeline_stage(
    db: Session,
    tenant: TenantContext,
    *,
    slug: str,
    name: str,
    position: int,
    stage_kind: str = "open",
) -> dict:
    clean_slug = slug.strip().lower()
    clean_name = name.strip()
    if not SLUG_RE.fullmatch(clean_slug):
        raise HTTPException(status_code=422, detail="Stage slug must match ^[a-z0-9][a-z0-9_-]{1,47}$")
    if not clean_name or len(clean_name) > 80:
        raise HTTPException(status_code=422, detail="Stage name must be 1..80 characters")
    if stage_kind not in ("open", "won", "lost"):
        raise HTTPException(status_code=422, detail="stage_kind must be open, won, or lost")
    if position < 0:
        raise HTTPException(status_code=422, detail="position must be >= 0")

    current = _now()
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    _ensure_default_stages_in_tx(db, current)

    existing = db.scalar(select(PipelineStage).where(PipelineStage.slug == clean_slug))
    if existing is not None:
        db.rollback()
        raise HTTPException(status_code=409, detail="Pipeline stage slug already exists")

    stage = PipelineStage(
        slug=clean_slug,
        name=clean_name,
        position=position,
        stage_kind=stage_kind,
        is_active=True,
        created_at=current,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return _stage_to_dict(stage)


def create_opportunity(
    db: Session,
    tenant: TenantContext,
    *,
    title: str,
    contact_id: int | None = None,
    lead_id: int | None = None,
    conversation_id: int | None = None,
    stage_id: int | None = None,
    owner_user_id: str | None = None,
    amount: Decimal | None = None,
    currency: str = "USD",
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict:
    clean_title = title.strip()
    if not clean_title or len(clean_title) > 160:
        raise HTTPException(status_code=422, detail="Opportunity title must be 1..160 characters")
    if amount is not None and amount < 0:
        raise HTTPException(status_code=422, detail="Opportunity amount must be non-negative")
    norm_currency = _normalize_currency(currency)
    if contact_id is None and lead_id is None:
        raise HTTPException(status_code=422, detail="Either contact_id or lead_id is required")

    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    _ensure_default_stages_in_tx(db, current)

    if lead_id is not None:
        lead = db.get(Lead, lead_id)
        if lead is None:
            db.rollback()
            raise HTTPException(status_code=404, detail="Lead not found")
        if contact_id is None:
            contact_id = lead.cliente_id
        elif lead.cliente_id != contact_id:
            db.rollback()
            raise HTTPException(status_code=422, detail="Lead does not belong to the specified contact")

    if db.get(Cliente, contact_id) is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Contact not found")

    if conversation_id is not None and db.get(Conversation, conversation_id) is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Conversation not found")

    if stage_id is not None:
        stage = db.get(PipelineStage, stage_id)
        if stage is None or not stage.is_active:
            db.rollback()
            raise HTTPException(status_code=404, detail="Pipeline stage not found")
    else:
        stage = db.scalar(
            select(PipelineStage)
            .where(PipelineStage.stage_kind == "open", PipelineStage.is_active.is_(True))
            .order_by(PipelineStage.position.asc(), PipelineStage.id.asc())
            .limit(1)
        )
        if stage is None:
            db.rollback()
            raise HTTPException(status_code=409, detail="No active open pipeline stage available")

    opp = Opportunity(
        contact_id=contact_id,
        lead_id=lead_id,
        conversation_id=conversation_id,
        stage_id=stage.id,
        title=clean_title,
        owner_user_id=owner_user_id.strip()[:64] if owner_user_id else None,
        amount=amount,
        currency=norm_currency,
        outcome=stage.stage_kind,
        version=1,
        closed_at=current if stage.stage_kind in ("won", "lost") else None,
        created_at=current,
        updated_at=current,
    )
    db.add(opp)
    db.flush()

    activity = OpportunityActivity(
        opportunity_id=opp.id,
        activity_type="created",
        actor_user_id=actor_user_id[:64] if actor_user_id else None,
        to_stage_id=stage.id,
        metadata_json={"stage_slug": stage.slug, "owner_user_id": opp.owner_user_id},
        created_at=current,
    )
    db.add(activity)
    create_system_event(
        db,
        "opportunity.created",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"opportunity_id": opp.id, "contact_id": opp.contact_id, "lead_id": opp.lead_id, "stage_slug": stage.slug},
    )
    db.commit()
    db.refresh(opp)
    db.refresh(activity)
    return _opportunity_to_dict(opp, stage, [activity])


def list_opportunities(
    db: Session,
    tenant: TenantContext,
    *,
    limit: int = 50,
    offset: int = 0,
    stage_id: int | None = None,
    owner_user_id: str | None = None,
    outcome: str | None = None,
    contact_id: int | None = None,
    lead_id: int | None = None,
) -> tuple[list[dict], int]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    stmt = select(Opportunity, PipelineStage).join(PipelineStage, Opportunity.stage_id == PipelineStage.id)
    if stage_id is not None:
        stmt = stmt.where(Opportunity.stage_id == stage_id)
    if owner_user_id is not None:
        stmt = stmt.where(Opportunity.owner_user_id == owner_user_id)
    if outcome is not None:
        stmt = stmt.where(Opportunity.outcome == outcome)
    if contact_id is not None:
        stmt = stmt.where(Opportunity.contact_id == contact_id)
    if lead_id is not None:
        stmt = stmt.where(Opportunity.lead_id == lead_id)

    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(
        stmt.order_by(Opportunity.updated_at.desc(), Opportunity.id.desc()).offset(offset).limit(limit)
    ).all()
    return [_opportunity_to_dict(opp, stage) for opp, stage in rows], total


def get_opportunity(db: Session, tenant: TenantContext, opportunity_id: int) -> dict:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    row = db.execute(
        select(Opportunity, PipelineStage)
        .join(PipelineStage, Opportunity.stage_id == PipelineStage.id)
        .where(Opportunity.id == opportunity_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    opp, stage = row
    activities = list(
        db.scalars(
            select(OpportunityActivity)
            .where(OpportunityActivity.opportunity_id == opportunity_id)
            .order_by(OpportunityActivity.id.asc())
        ).all()
    )
    return _opportunity_to_dict(opp, stage, activities)


def update_opportunity(
    db: Session,
    tenant: TenantContext,
    opportunity_id: int,
    *,
    expected_version: int,
    actor_user_id: str | None = None,
    title: str | None = None,
    stage_id: int | None = None,
    owner_user_id: object = _UNSET,
    amount: object = _UNSET,
    currency: str | None = None,
    outcome: str | None = None,
    close_reason: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Atomically update stage, owner, amount, or close outcome with optimistic version check."""
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    opp = db.scalar(select(Opportunity).where(Opportunity.id == opportunity_id).with_for_update())
    if opp is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Opportunity not found")
    if opp.version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale opportunity version")

    previous_stage = db.get(PipelineStage, opp.stage_id)
    target_stage = previous_stage
    stage_changed = False

    if stage_id is not None and stage_id != opp.stage_id:
        candidate = db.get(PipelineStage, stage_id)
        if candidate is None or not candidate.is_active:
            db.rollback()
            raise HTTPException(status_code=404, detail="Pipeline stage not found")
        target_stage = candidate
        opp.stage_id = candidate.id
        stage_changed = True

    if title is not None:
        clean_title = title.strip()
        if not clean_title or len(clean_title) > 160:
            db.rollback()
            raise HTTPException(status_code=422, detail="Opportunity title must be 1..160 characters")
        opp.title = clean_title

    owner_changed = False
    if owner_user_id is not _UNSET:
        new_owner = owner_user_id.strip()[:64] if isinstance(owner_user_id, str) and owner_user_id.strip() else None
        if new_owner != opp.owner_user_id:
            opp.owner_user_id = new_owner
            owner_changed = True

    if amount is not _UNSET:
        if amount is not None and amount < 0:
            db.rollback()
            raise HTTPException(status_code=422, detail="Opportunity amount must be non-negative")
        opp.amount = amount

    if currency is not None:
        opp.currency = _normalize_currency(currency)

    # Determine effective outcome from explicit outcome or target stage kind.
    effective_outcome = outcome if outcome is not None else (target_stage.stage_kind if stage_changed else opp.outcome)
    if effective_outcome not in ("open", "won", "lost"):
        db.rollback()
        raise HTTPException(status_code=422, detail="outcome must be open, won, or lost")

    # If explicitly closing without passing a closed stage_id, align stage to matching won/lost stage if available.
    if outcome in ("won", "lost") and target_stage.stage_kind != outcome:
        matching_stage = db.scalar(
            select(PipelineStage)
            .where(PipelineStage.stage_kind == outcome, PipelineStage.is_active.is_(True))
            .order_by(PipelineStage.position.asc(), PipelineStage.id.asc())
            .limit(1)
        )
        if matching_stage is not None:
            target_stage = matching_stage
            opp.stage_id = matching_stage.id
            stage_changed = True

    clean_reason = close_reason.strip()[:240] if close_reason else None
    if effective_outcome == "lost" and not clean_reason and not opp.close_reason:
        db.rollback()
        raise HTTPException(status_code=422, detail="close_reason is required when closing an opportunity as lost")

    previous_outcome = opp.outcome
    opp.outcome = effective_outcome
    if effective_outcome in ("won", "lost"):
        opp.closed_at = opp.closed_at or current
        if clean_reason is not None:
            opp.close_reason = clean_reason
    else:
        opp.closed_at = None
        opp.close_reason = None

    opp.version += 1
    opp.updated_at = current

    actor = actor_user_id[:64] if actor_user_id else None
    if stage_changed:
        db.add(
            OpportunityActivity(
                opportunity_id=opp.id,
                activity_type="stage_changed",
                actor_user_id=actor,
                from_stage_id=previous_stage.id,
                to_stage_id=target_stage.id,
                note=note.strip() if note else None,
                metadata_json={"from_stage": previous_stage.slug, "to_stage": target_stage.slug, "version": opp.version},
                created_at=current,
            )
        )
        create_system_event(
            db,
            "opportunity.stage.changed",
            tenant.auth_tenant_id,
            tenant.schema_name,
            {
                "opportunity_id": opp.id,
                "from_stage": previous_stage.slug,
                "to_stage": target_stage.slug,
                "version": opp.version,
                "actor_user_id": actor,
            },
        )

    if owner_changed:
        db.add(
            OpportunityActivity(
                opportunity_id=opp.id,
                activity_type="owner_changed",
                actor_user_id=actor,
                metadata_json={"owner_user_id": opp.owner_user_id, "version": opp.version},
                created_at=current,
            )
        )

    if effective_outcome in ("won", "lost") and effective_outcome != previous_outcome:
        event_name = "opportunity.won" if effective_outcome == "won" else "opportunity.lost"
        activity_kind = "closed_won" if effective_outcome == "won" else "closed_lost"
        db.add(
            OpportunityActivity(
                opportunity_id=opp.id,
                activity_type=activity_kind,
                actor_user_id=actor,
                to_stage_id=target_stage.id,
                note=opp.close_reason,
                metadata_json={"outcome": effective_outcome, "amount": str(opp.amount) if opp.amount is not None else None, "currency": opp.currency},
                created_at=current,
            )
        )
        create_system_event(
            db,
            event_name,
            tenant.auth_tenant_id,
            tenant.schema_name,
            {
                "opportunity_id": opp.id,
                "contact_id": opp.contact_id,
                "outcome": effective_outcome,
                "close_reason": opp.close_reason,
                "version": opp.version,
                "actor_user_id": actor,
            },
        )
    elif not stage_changed and not owner_changed:
        db.add(
            OpportunityActivity(
                opportunity_id=opp.id,
                activity_type="updated",
                actor_user_id=actor,
                note=note.strip() if note else None,
                metadata_json={"version": opp.version},
                created_at=current,
            )
        )

    db.commit()
    return get_opportunity(db, tenant, opp.id)


def add_opportunity_activity(
    db: Session,
    tenant: TenantContext,
    opportunity_id: int,
    *,
    actor_user_id: str | None,
    note: str,
    now: datetime | None = None,
) -> dict:
    clean_note = note.strip()
    if not clean_note:
        raise HTTPException(status_code=422, detail="Activity note must not be empty")
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    if db.get(Opportunity, opportunity_id) is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    activity = OpportunityActivity(
        opportunity_id=opportunity_id,
        activity_type="note",
        actor_user_id=actor_user_id[:64] if actor_user_id else None,
        note=clean_note,
        metadata_json={},
        created_at=current,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return _activity_to_dict(activity)
