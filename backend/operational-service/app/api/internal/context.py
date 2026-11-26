from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_internal_token
from app.core.tenant_resolver import TenantContext, ensure_runtime_is_usable
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.context import (
    ActiveAgentResolvedOut,
    AgentRuleCreateIn,
    AgentRuleOut,
    AgentRulePatchIn,
    AgentTraceCreateIn,
    AgentTraceOut,
    BusinessContextStatusRead,
    ContextDocumentCreate,
    ContextDocumentPatch,
    ContextDocumentRead,
    ContextRetrieveRequest,
    ContextSourceRead,
    InternalAIUsageCreateIn,
    InternalProposalCreateIn,
    SetupGenerateOut,
    SetupMessageIn,
    SetupSessionCreateIn,
    SetupSessionOut,
)
from app.services.agent_service import resolve_runtime_agent
from app.services.ai_extensions_service import record_ai_usage
from app.services.ai_proposal_service import create_ai_proposal
from app.services.context_service import (
    append_setup_message,
    context_status,
    create_agent_rule,
    create_agent_trace,
    create_context_document,
    create_setup_session,
    delete_agent_rule,
    delete_context_document,
    generate_setup_context,
    get_agent_trace,
    get_context_document,
    list_agent_rules,
    list_context_documents,
    list_conversation_memory_by_ref,
    list_conversation_traces,
    patch_agent_rule,
    patch_context_document,
    retrieve_context_sources,
)


router = APIRouter(
    prefix="/internal/tenants/{tenant_id}/context",
    tags=["Internal Context"],
    dependencies=[Depends(require_internal_token)],
)


def resolve_internal_tenant(tenant_id: int, db: Session) -> TenantContext:
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == tenant_id))
    if not runtime:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant runtime not provisioned")
    ensure_runtime_is_usable(runtime)
    return TenantContext(
        auth_tenant_id=runtime.auth_tenant_id,
        tenant_slug=runtime.tenant_slug,
        schema_name=runtime.schema_name,
        tenant_code=runtime.tenant_code,
        plan=runtime.plan,
        status=runtime.status,
    )


@router.post("/documents", response_model=ContextDocumentRead, status_code=status.HTTP_201_CREATED)
def create_document(tenant_id: int, payload: ContextDocumentCreate, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return create_context_document(db, tenant, payload)


@router.get("/documents", response_model=list[ContextDocumentRead])
def list_documents(tenant_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return list_context_documents(db, tenant)


@router.get("/documents/{document_id}", response_model=ContextDocumentRead)
def get_document(tenant_id: int, document_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return get_context_document(db, tenant, document_id)


@router.patch("/documents/{document_id}", response_model=ContextDocumentRead)
def patch_document(
    tenant_id: int, document_id: int, payload: ContextDocumentPatch, db: Session = Depends(get_db),
):
    tenant = resolve_internal_tenant(tenant_id, db)
    return patch_context_document(db, tenant, document_id, payload)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(tenant_id: int, document_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    delete_context_document(db, tenant, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/status", response_model=BusinessContextStatusRead)
def get_status(tenant_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return context_status(db, tenant)


@router.post("/retrieve", response_model=list[ContextSourceRead])
def retrieve(tenant_id: int, payload: ContextRetrieveRequest, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return retrieve_context_sources(db, tenant, payload.query, payload.limit, document_ids=payload.document_ids)


@router.get("/rules", response_model=list[AgentRuleOut])
def rules_list(tenant_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return list_agent_rules(db, tenant)


@router.post("/rules", response_model=AgentRuleOut, status_code=status.HTTP_201_CREATED)
def rules_create(tenant_id: int, payload: AgentRuleCreateIn, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return create_agent_rule(db, tenant, payload)


@router.patch("/rules/{rule_id}", response_model=AgentRuleOut)
def rules_patch(tenant_id: int, rule_id: int, payload: AgentRulePatchIn, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return patch_agent_rule(db, tenant, rule_id, payload)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def rules_delete(tenant_id: int, rule_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    delete_agent_rule(db, tenant, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/traces", response_model=AgentTraceOut, status_code=status.HTTP_201_CREATED)
def traces_create(tenant_id: int, payload: AgentTraceCreateIn, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return create_agent_trace(db, tenant, payload)


@router.get("/traces/{trace_id}", response_model=AgentTraceOut)
def traces_get(tenant_id: int, trace_id: int, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return get_agent_trace(db, tenant, trace_id)


@router.get("/conversations/{conversation_id}/traces", response_model=list[AgentTraceOut])
def traces_for_conversation(tenant_id: int, conversation_id: str, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return list_conversation_traces(db, tenant, conversation_id)


@router.post("/setup-sessions", response_model=SetupSessionOut, status_code=status.HTTP_201_CREATED)
def setup_create(tenant_id: int, payload: SetupSessionCreateIn, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return create_setup_session(db, tenant, objective=payload.objective)


@router.post("/setup-sessions/{session_id}/messages", response_model=SetupSessionOut)
def setup_message(
    tenant_id: int, session_id: str, payload: SetupMessageIn, db: Session = Depends(get_db),
):
    tenant = resolve_internal_tenant(tenant_id, db)
    return append_setup_message(db, tenant, session_id, content=payload.content)


@router.post("/setup-sessions/{session_id}/generate-context", response_model=SetupGenerateOut)
def setup_generate(tenant_id: int, session_id: str, db: Session = Depends(get_db)):
    tenant = resolve_internal_tenant(tenant_id, db)
    return generate_setup_context(db, tenant, session_id)


@router.get("/agents/resolve", response_model=ActiveAgentResolvedOut | None)
def resolve_active_agent_endpoint(
    tenant_id: int,
    agent_id: int | None = Query(default=None, ge=1),
    agent_revision_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    tenant = resolve_internal_tenant(tenant_id, db)
    return resolve_runtime_agent(db, tenant, agent_id=agent_id, agent_revision_id=agent_revision_id)


@router.get("/conversations/{conversation_id}/memory")
def conversation_memory_endpoint(
    tenant_id: int,
    conversation_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    tenant = resolve_internal_tenant(tenant_id, db)
    return list_conversation_memory_by_ref(db, tenant, conversation_id, limit=limit)


@router.post("/proposals", status_code=status.HTTP_201_CREATED)
def create_proposal_internal(
    tenant_id: int,
    payload: InternalProposalCreateIn,
    db: Session = Depends(get_db),
):
    tenant = resolve_internal_tenant(tenant_id, db)
    return create_ai_proposal(
        db,
        tenant,
        action_type=payload.action_type,
        resource_id=payload.resource_id,
        arguments=payload.arguments,
        idempotency_key=payload.idempotency_key,
        proposed_by=payload.proposed_by,
        rationale=payload.rationale,
    )


@router.post("/ai-usage", status_code=status.HTTP_201_CREATED)
def record_ai_usage_internal(
    tenant_id: int,
    payload: InternalAIUsageCreateIn,
    db: Session = Depends(get_db),
):
    tenant = resolve_internal_tenant(tenant_id, db)
    return record_ai_usage(
        db,
        tenant,
        provider=payload.provider,
        model=payload.model,
        prompt_tokens=payload.prompt_tokens,
        completion_tokens=payload.completion_tokens,
        latency_ms=payload.latency_ms,
        estimated_cost_usd=payload.estimated_cost_usd,
        is_simulation=payload.is_simulation,
        agent_id=payload.agent_id,
        agent_revision_id=payload.agent_revision_id,
        pricing_version=payload.pricing_version,
    )
