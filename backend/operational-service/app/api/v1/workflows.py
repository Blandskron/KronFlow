"""Workflow authoring, validation, simulation, publication, and run execution routes."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, require_permission
from app.core.tenant_resolver import TenantContext, resolve_crm_editor, resolve_tenant_from_jwt
from app.schemas.workflow import (
    WorkflowCreateIn,
    WorkflowDraftUpdateIn,
    WorkflowOut,
    WorkflowPublishIn,
    WorkflowRevisionOut,
    WorkflowRunOut,
    WorkflowSimulateIn,
    WorkflowSimulationOut,
    WorkflowTemplateOut,
    WorkflowValidationOut,
)
from app.services.workflow_service import (
    cancel_workflow_run,
    create_workflow,
    get_workflow,
    get_workflow_run,
    list_workflow_revisions,
    list_workflow_runs,
    list_workflow_templates,
    list_workflows,
    process_tenant_workflows,
    publish_workflow,
    simulate_workflow,
    update_workflow_draft,
    validate_saved_workflow,
)


router = APIRouter(prefix="/api/v1", tags=["Workflows"])


@router.get("/workflows/templates", response_model=list[WorkflowTemplateOut])
def workflow_templates_endpoint(tenant: TenantContext = Depends(resolve_tenant_from_jwt)):
    _ = tenant
    return list_workflow_templates()


@router.get("/workflows", response_model=list[WorkflowOut])
def list_workflows_endpoint(
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_workflows(db, tenant)


@router.post("/workflows", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow_endpoint(
    payload: WorkflowCreateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return create_workflow(db, tenant, payload, actor_user_id=principal.user_id)


@router.post("/workflows/process-tick")
def process_workflows_tick_endpoint(
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return process_tenant_workflows(db, tenant)


@router.get("/workflows/{workflow_id}", response_model=WorkflowOut)
def get_workflow_endpoint(
    workflow_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return get_workflow(db, tenant, workflow_id)


@router.patch("/workflows/{workflow_id}/draft", response_model=WorkflowOut)
def update_workflow_draft_endpoint(
    workflow_id: int,
    payload: WorkflowDraftUpdateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return update_workflow_draft(db, tenant, workflow_id, payload)


@router.post("/workflows/{workflow_id}/validate", response_model=WorkflowValidationOut)
def validate_workflow_endpoint(
    workflow_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return validate_saved_workflow(db, tenant, workflow_id)


@router.post("/workflows/{workflow_id}/simulate", response_model=WorkflowSimulationOut)
def simulate_workflow_endpoint(
    workflow_id: int,
    payload: WorkflowSimulateIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return simulate_workflow(db, tenant, workflow_id, payload.sample_payload)


@router.post("/workflows/{workflow_id}/publish", response_model=WorkflowRevisionOut)
def publish_workflow_endpoint(
    workflow_id: int,
    payload: WorkflowPublishIn,
    tenant: TenantContext = Depends(resolve_crm_editor),
    principal: CurrentPrincipal = Depends(require_permission("crm.manage")),
    db: Session = Depends(get_db),
):
    return publish_workflow(
        db,
        tenant,
        workflow_id,
        expected_version=payload.expected_version,
        actor_user_id=principal.user_id,
        note=payload.note,
    )


@router.get("/workflows/{workflow_id}/revisions", response_model=list[WorkflowRevisionOut])
def list_workflow_revisions_endpoint(
    workflow_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_workflow_revisions(db, tenant, workflow_id)


@router.get("/workflow-runs", response_model=list[WorkflowRunOut])
def list_workflow_runs_endpoint(
    workflow_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status", max_length=24),
    limit: int = Query(default=50, ge=1, le=100),
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return list_workflow_runs(db, tenant, workflow_id=workflow_id, status_filter=status_filter, limit=limit)


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRunOut)
def get_workflow_run_endpoint(
    run_id: int,
    tenant: TenantContext = Depends(resolve_tenant_from_jwt),
    db: Session = Depends(get_db),
):
    return get_workflow_run(db, tenant, run_id)


@router.post("/workflow-runs/{run_id}/cancel", response_model=WorkflowRunOut)
def cancel_workflow_run_endpoint(
    run_id: int,
    tenant: TenantContext = Depends(resolve_crm_editor),
    db: Session = Depends(get_db),
):
    return cancel_workflow_run(db, tenant, run_id)
