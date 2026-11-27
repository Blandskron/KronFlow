"""Tenant-scoped subprocessor approval registry and transfer gate (PRV-020)."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.privacy_lifecycle import TenantSubprocessorApproval


SUBPROCESSOR_LIST_VERSION = "2026-11-v1"

SUBPROCESSOR_CATALOG: dict[str, dict[str, str]] = {
    "groq": {"name": "Groq Inc.", "jurisdiction": "US", "purpose": "Inferencia LLM externa"},
    "resend": {"name": "Resend Inc.", "jurisdiction": "US", "purpose": "Correo transaccional y campañas"},
    "meta": {"name": "Meta Platforms", "jurisdiction": "US", "purpose": "WhatsApp / Instagram / Messenger"},
    "twilio": {"name": "Twilio Inc.", "jurisdiction": "US", "purpose": "Telefonía y voz programable"},
    "shopify": {"name": "Shopify Inc.", "jurisdiction": "CA/US", "purpose": "Comercio electrónico y pedidos"},
    "mercadopago": {"name": "Mercado Pago", "jurisdiction": "LATAM", "purpose": "Pagos y conciliación"},
    "google": {"name": "Google LLC", "jurisdiction": "US", "purpose": "SSO / Google Calendar"},
    "hubspot": {"name": "HubSpot Inc.", "jurisdiction": "US", "purpose": "Sincronización CRM externa"},
    "remote_mcp": {"name": "Servidor MCP Remoto", "jurisdiction": "EXTERNAL", "purpose": "Herramientas IA remotas"},
}


def list_subprocessors(db: Session, tenant: TenantContext) -> list[dict]:
    bind_tenant_session(db, tenant.schema_name)
    approvals: dict[str, TenantSubprocessorApproval] = {}
    if inspect(db.connection()).has_table(TenantSubprocessorApproval.__tablename__, schema=tenant.schema_name):
        for row in db.scalars(select(TenantSubprocessorApproval)).all():
            approvals[row.provider_key] = row

    items: list[dict] = []
    for key, meta in SUBPROCESSOR_CATALOG.items():
        row = approvals.get(key)
        items.append(
            {
                "provider_key": key,
                "name": meta["name"],
                "jurisdiction": row.jurisdiction if row else meta["jurisdiction"],
                "purpose": meta["purpose"],
                "subprocessor_list_version": row.subprocessor_list_version if row else SUBPROCESSOR_LIST_VERSION,
                "approved": bool(row.approved) if row else False,
                "approved_by": row.approved_by if row else None,
                "approved_at": row.approved_at if row else None,
                "revoked_at": row.revoked_at if row else None,
            }
        )
    return items


def set_subprocessor_approval(
    db: Session,
    tenant: TenantContext,
    *,
    provider_key: str,
    approved: bool,
    actor_user_id: str,
    subprocessor_list_version: str = SUBPROCESSOR_LIST_VERSION,
    now: datetime | None = None,
) -> dict:
    clean_key = provider_key.strip().lower()
    if clean_key not in SUBPROCESSOR_CATALOG:
        raise HTTPException(status_code=422, detail=f"Unknown subprocessor provider_key: {provider_key}")

    current = now.astimezone(UTC) if now is not None else datetime.now(UTC)
    bind_tenant_session(db, tenant.schema_name)
    if not inspect(db.connection()).has_table(TenantSubprocessorApproval.__tablename__, schema=tenant.schema_name):
        raise HTTPException(status_code=503, detail="Subprocessor registry schema is unavailable")

    meta = SUBPROCESSOR_CATALOG[clean_key]
    values = {
        "jurisdiction": meta["jurisdiction"],
        "subprocessor_list_version": subprocessor_list_version.strip()[:32] or SUBPROCESSOR_LIST_VERSION,
        "approved": bool(approved),
        "approved_by": actor_user_id[:64],
        "approved_at": current if approved else None,
        "revoked_at": None if approved else current,
        "updated_at": current,
    }
    db.execute(
        insert(TenantSubprocessorApproval)
        .values(provider_key=clean_key, **values)
        .on_conflict_do_update(index_elements=["provider_key"], set_=values)
    )
    create_system_event(
        db,
        "privacy.subprocessor.updated",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {
            "provider_key": clean_key,
            "jurisdiction": meta["jurisdiction"],
            "approved": bool(approved),
            "subprocessor_list_version": values["subprocessor_list_version"],
            "actor_user_id": actor_user_id,
        },
    )
    db.commit()
    return {
        "provider_key": clean_key,
        "name": meta["name"],
        "jurisdiction": meta["jurisdiction"],
        "purpose": meta["purpose"],
        **values,
    }


def is_subprocessor_approved_in_tx(db: Session, tenant: TenantContext, provider_key: str) -> bool:
    clean_key = provider_key.strip().lower()
    if not inspect(db.connection()).has_table(TenantSubprocessorApproval.__tablename__, schema=tenant.schema_name):
        return False
    row = db.scalar(
        select(TenantSubprocessorApproval).where(TenantSubprocessorApproval.provider_key == clean_key)
    )
    return bool(row and row.approved)
