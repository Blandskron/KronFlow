"""Security & privacy incident register with automated 3h CSIRT (Ley 21.663) and 72h GDPR/Ley 21.719 SLAs (PRV-024)."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.security_incident import SecurityIncident
from app.services.tenant_provisioning_service import create_system_event


VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
VALID_STATUSES = frozenset({"open", "contained", "notified", "closed"})


def compute_incident_sla_deadlines(detected_at: datetime) -> tuple[datetime, datetime]:
    """Return (csirt_early_warning_due_at [+3h], authority_notice_due_at [+72h])."""
    base = detected_at.astimezone(UTC) if detected_at.tzinfo else detected_at.replace(tzinfo=UTC)
    return base + timedelta(hours=3), base + timedelta(hours=72)


def _to_dict(row: SecurityIncident) -> dict:
    return {
        "id": row.id,
        "auth_tenant_id": row.auth_tenant_id,
        "severity": row.severity,
        "status": row.status,
        "title": row.title,
        "summary": row.summary,
        "affected_records_estimate": row.affected_records_estimate,
        "detected_at": row.detected_at,
        "csirt_early_warning_due_at": row.csirt_early_warning_due_at,
        "authority_notice_due_at": row.authority_notice_due_at,
        "containment_notes": row.containment_notes,
        "reported_by": row.reported_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_security_incidents(db: Session, tenant: TenantContext) -> list[dict]:
    rows = list(
        db.scalars(
            select(SecurityIncident)
            .where(SecurityIncident.auth_tenant_id == tenant.auth_tenant_id)
            .order_by(SecurityIncident.detected_at.desc(), SecurityIncident.id.desc())
        ).all()
    )
    return [_to_dict(r) for r in rows]


def create_security_incident(
    db: Session,
    tenant: TenantContext,
    *,
    severity: str,
    title: str,
    summary: str,
    affected_records_estimate: int = 0,
    detected_at: datetime | None = None,
    containment_notes: str | None = None,
    actor_user_id: str,
) -> dict:
    sev = severity.strip().lower()
    if sev not in VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail=f"Invalid severity: {severity}")
    detected = (detected_at.astimezone(UTC) if detected_at.tzinfo else detected_at.replace(tzinfo=UTC)) if detected_at else datetime.now(UTC)
    csirt_due, authority_due = compute_incident_sla_deadlines(detected)
    now = datetime.now(UTC)
    row = SecurityIncident(
        auth_tenant_id=tenant.auth_tenant_id,
        severity=sev,
        status="open",
        title=title.strip()[:180],
        summary=summary.strip(),
        affected_records_estimate=max(0, int(affected_records_estimate)),
        detected_at=detected,
        csirt_early_warning_due_at=csirt_due,
        authority_notice_due_at=authority_due,
        containment_notes=containment_notes.strip() if containment_notes else None,
        reported_by=actor_user_id[:64],
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    create_system_event(
        db,
        "security.incident.opened",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "incident_id": row.id,
            "severity": row.severity,
            "csirt_early_warning_due_at": csirt_due.isoformat(),
            "authority_notice_due_at": authority_due.isoformat(),
            "actor_user_id": actor_user_id,
        },
    )
    db.commit()
    db.refresh(row)
    return _to_dict(row)


def update_security_incident(
    db: Session,
    tenant: TenantContext,
    incident_id: int,
    *,
    status_value: str | None = None,
    containment_notes: str | None = None,
    actor_user_id: str,
) -> dict:
    row = db.scalar(
        select(SecurityIncident)
        .where(SecurityIncident.id == incident_id, SecurityIncident.auth_tenant_id == tenant.auth_tenant_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Security incident not found")
    if status_value is not None:
        st = status_value.strip().lower()
        if st not in VALID_STATUSES:
            raise HTTPException(status_code=422, detail=f"Invalid incident status: {status_value}")
        row.status = st
    if containment_notes is not None:
        row.containment_notes = containment_notes.strip() or None
    row.updated_at = datetime.now(UTC)
    create_system_event(
        db,
        "security.incident.updated",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"incident_id": row.id, "status": row.status, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(row)
    return _to_dict(row)
