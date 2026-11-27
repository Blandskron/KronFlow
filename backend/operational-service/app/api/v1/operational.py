from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_audit_reader, resolve_tenant_from_jwt
from app.schemas.audit_event import AuditEventPage
from app.schemas.privacy_case import (
    CaseState,
    PrivacyCaseCreateIn,
    PrivacyCaseExportOut,
    PrivacyCaseOut,
    PrivacyCasePage,
    PrivacyCaseTransition,
    PrivacyErasureIn,
    PrivacyErasureOut,
    PrivacyRectifyIn,
    PrivacyRestrictIn,
    RetentionSweepIn,
    RetentionSweepOut,
    SecurityIncidentCreateIn,
    SecurityIncidentUpdateIn,
    SubprocessorApprovalIn,
    TenantAIPolicyOut,
    TenantAIPolicyUpdateIn,
    TenantRetentionPolicyOut,
    TenantRetentionPolicyUpdateIn,
)
from app.services.conversation_control_service import get_tenant_ai_policy, set_tenant_ai_policy
from app.services.security_incident_service import (
    create_security_incident,
    list_security_incidents,
    update_security_incident,
)
from app.services.subprocessor_service import list_subprocessors, set_subprocessor_approval
from app.services.operational_read_service import (
    list_clientes,
    list_conversaciones,
    list_ejecutivos,
    list_inventario,
    list_leads_operational,
    list_log_limpiezas,
    list_mensajes_dashboard,
    list_solicitudes_derechos,
)
from app.services.privacy_case_service import (
    create_privacy_case,
    execute_privacy_erasure,
    export_privacy_case_data,
    get_tenant_retention_policy,
    list_privacy_cases,
    rectify_privacy_case_subject,
    run_retention_sweep,
    set_privacy_case_restriction,
    set_tenant_retention_policy,
    transition_privacy_case,
    verify_tenant_cleanup_chain,
)
from app.services.audit_event_service import list_audit_events

router = APIRouter(prefix="/api/v1/operational", tags=["Operational Data"])


def page_size(limit: int, settings: Settings) -> int:
    return min(limit, settings.max_page_size)


@router.get("/audit-events", response_model=AuditEventPage)
def audit_events(
    limit: int = Query(default=25, ge=1, le=50),
    before_id: int | None = Query(default=None, ge=1, le=2147483647),
    event_type: str | None = Query(default=None, max_length=80),
    correlation_id: UUID | None = None,
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
):
    return list_audit_events(db, tenant, limit, before_id, event_type, correlation_id)


@router.get("/clientes")
def clientes(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_clientes(db, tenant, page_size(limit, settings), offset)


@router.get("/leads")
def leads(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_leads_operational(db, tenant, page_size(limit, settings), offset)


@router.get("/inventario-vehiculos")
def inventario_vehiculos(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    disponible: bool | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_inventario(db, tenant, page_size(limit, settings), offset, disponible)


@router.get("/conversaciones")
def conversaciones(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_conversaciones(db, tenant, page_size(limit, settings), offset)


@router.get("/mensajes-dashboard")
def mensajes_dashboard(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    whatsapp_id: str | None = None,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_mensajes_dashboard(db, tenant, page_size(limit, settings), offset, whatsapp_id)


@router.get("/solicitudes-derechos")
def solicitudes_derechos(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_solicitudes_derechos(db, tenant, page_size(limit, settings), offset)


@router.get("/privacy-cases", response_model=PrivacyCasePage)
def privacy_cases(
    state: CaseState | None = None,
    limit: int = Query(default=25, ge=1, le=50), offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
):
    return list_privacy_cases(db, tenant, state, limit, offset)


@router.post("/privacy-cases", response_model=PrivacyCaseOut, status_code=201)
def create_privacy_case_endpoint(
    payload: PrivacyCaseCreateIn,
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return create_privacy_case(db, tenant, payload, actor_id=principal.user_id)


@router.post("/privacy-cases/{case_id}/rectify")
def rectify_privacy_case_endpoint(
    payload: PrivacyRectifyIn,
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return rectify_privacy_case_subject(
        db,
        tenant,
        case_id,
        nombre=payload.nombre,
        email=payload.email,
        telefono=payload.telefono,
        actor_id=principal.user_id,
    )


@router.post("/privacy-cases/{case_id}/restrict")
def restrict_privacy_case_endpoint(
    payload: PrivacyRestrictIn,
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return set_privacy_case_restriction(
        db,
        tenant,
        case_id,
        restricted=payload.restricted,
        reason=payload.reason,
        actor_id=principal.user_id,
    )


@router.patch("/privacy-cases/{case_id}", response_model=PrivacyCaseOut)
def change_privacy_case(
    transition: PrivacyCaseTransition,
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader), db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return transition_privacy_case(db, tenant, case_id, transition, principal.user_id)


@router.post("/privacy-cases/{case_id}/export", response_model=PrivacyCaseExportOut)
def export_privacy_case(
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return export_privacy_case_data(db, tenant, case_id, actor_id=principal.user_id)


@router.post("/privacy-cases/{case_id}/erase", response_model=PrivacyErasureOut)
def erase_privacy_case(
    payload: PrivacyErasureIn,
    case_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return execute_privacy_erasure(db, tenant, case_id, actor_id=principal.user_id, confirmed=payload.confirmed)


@router.post("/retention/sweep", response_model=RetentionSweepOut)
def retention_sweep(
    payload: RetentionSweepIn,
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return run_retention_sweep(
        db, tenant, message_retention_days=payload.message_retention_days, actor_id=principal.user_id,
    )


@router.get("/ejecutivos")
def ejecutivos(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_ejecutivos(db, tenant, page_size(limit, settings), offset)


@router.get("/log-limpiezas")
def log_limpiezas(
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    return list_log_limpiezas(db, tenant, page_size(limit, settings), offset)


@router.get("/ai-policy", response_model=TenantAIPolicyOut)
def ai_policy_read(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return get_tenant_ai_policy(db, tenant)


@router.put("/ai-policy", response_model=TenantAIPolicyOut)
def ai_policy_update(
    payload: TenantAIPolicyUpdateIn,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return set_tenant_ai_policy(
        db,
        tenant,
        ai_enabled=payload.ai_enabled,
        allow_external_ai_transfer=payload.allow_external_ai_transfer,
        memory_auto_capture=payload.memory_auto_capture,
        actor_user_id=principal.user_id,
        reason=payload.reason,
    )


@router.get("/retention-policy", response_model=TenantRetentionPolicyOut)
def retention_policy_read(
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
):
    return get_tenant_retention_policy(db, tenant)


@router.put("/retention-policy", response_model=TenantRetentionPolicyOut)
def retention_policy_update(
    payload: TenantRetentionPolicyUpdateIn,
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return set_tenant_retention_policy(
        db,
        tenant,
        messages_retention_days=payload.messages_retention_days,
        memory_retention_days=payload.memory_retention_days,
        attachments_retention_days=payload.attachments_retention_days,
        voice_retention_days=payload.voice_retention_days,
        traces_retention_days=payload.traces_retention_days,
        webchat_retention_days=payload.webchat_retention_days,
        legal_hold=payload.legal_hold,
        legal_hold_reason=payload.legal_hold_reason,
        actor_user_id=principal.user_id,
    )


@router.get("/subprocessors")
def subprocessors_list(
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
):
    return {"items": list_subprocessors(db, tenant)}


@router.put("/subprocessors/{provider_key}")
def subprocessor_approve(
    provider_key: str,
    payload: SubprocessorApprovalIn,
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return set_subprocessor_approval(
        db,
        tenant,
        provider_key=provider_key,
        approved=payload.approved,
        subprocessor_list_version=payload.subprocessor_list_version,
        actor_user_id=principal.user_id,
    )


@router.get("/log-limpiezas/verify-chain")
def log_limpiezas_verify_chain(
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
):
    return verify_tenant_cleanup_chain(db, tenant)


@router.get("/security-incidents")
def security_incidents_list(
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
):
    return {"items": list_security_incidents(db, tenant)}


@router.post("/security-incidents", status_code=201)
def security_incidents_create(
    payload: SecurityIncidentCreateIn,
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return create_security_incident(
        db,
        tenant,
        severity=payload.severity,
        title=payload.title,
        summary=payload.summary,
        affected_records_estimate=payload.affected_records_estimate,
        detected_at=payload.detected_at,
        containment_notes=payload.containment_notes,
        actor_user_id=principal.user_id,
    )


@router.patch("/security-incidents/{incident_id}")
def security_incidents_update(
    payload: SecurityIncidentUpdateIn,
    incident_id: int = Path(ge=1, le=9223372036854775807),
    tenant: TenantContext = Depends(resolve_audit_reader),
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
):
    return update_security_incident(
        db,
        tenant,
        incident_id,
        status_value=payload.status,
        containment_notes=payload.containment_notes,
        actor_user_id=principal.user_id,
    )
