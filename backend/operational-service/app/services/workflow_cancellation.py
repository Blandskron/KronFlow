"""Transactional workflow wait-run cancellation without service-layer cycles."""

from datetime import datetime, timezone

from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.tenant_models.workflows import WorkflowDefinition, WorkflowRevision, WorkflowRun, WorkflowStepRun


def cancel_waiting_runs_in_tx(
    db: Session,
    tenant: TenantContext,
    *,
    event_type: str,
    contact_id: int | None = None,
    conversation_id: int | None = None,
    reason: str,
    now: datetime | None = None,
) -> int:
    """Cancel matching waiting workflow runs inside the caller's active transaction."""
    existing = set(inspect(db.connection()).get_table_names(schema=tenant.schema_name))
    required = {
        WorkflowDefinition.__tablename__,
        WorkflowRevision.__tablename__,
        WorkflowRun.__tablename__,
        WorkflowStepRun.__tablename__,
    }
    if not required.issubset(existing) or (contact_id is None and conversation_id is None):
        return 0

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stmt = select(WorkflowRun).where(WorkflowRun.status == "waiting")
    if contact_id is not None and conversation_id is not None:
        stmt = stmt.where((WorkflowRun.contact_id == contact_id) | (WorkflowRun.conversation_id == conversation_id))
    elif contact_id is not None:
        stmt = stmt.where(WorkflowRun.contact_id == contact_id)
    else:
        stmt = stmt.where(WorkflowRun.conversation_id == conversation_id)

    waiting_runs = list(db.scalars(stmt.with_for_update()).all())
    cancelled = 0
    clean_reason = reason.strip()[:300]
    for run in waiting_runs:
        cancel_events = list(run.cancel_on_events or [])
        if cancel_events and event_type not in cancel_events:
            continue
        run.status = "cancelled"
        run.wake_at = None
        run.error_message = clean_reason
        run.updated_at = current
        run.finished_at = current
        db.execute(
            update(WorkflowStepRun)
            .where(WorkflowStepRun.run_id == run.id, WorkflowStepRun.status == "waiting")
            .values(status="cancelled", error_message=clean_reason, finished_at=current)
        )
        cancelled += 1
    return cancelled
