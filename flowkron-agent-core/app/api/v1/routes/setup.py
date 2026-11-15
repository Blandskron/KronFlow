from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.v1.schemas.setup import GeneratedContextRead, SetupMessageCreate, SetupSessionCreate, SetupSessionRead
from app.core.tenant import TenantContext, resolve_tenant

router = APIRouter(prefix="/api/v1/setup-chat", tags=["Setup Assistant"])


@router.post("/sessions", response_model=SetupSessionRead)
def create_setup_session(payload: SetupSessionCreate, tenant: TenantContext = Depends(resolve_tenant)):
    return SetupSessionRead(session_id=f"{tenant.tenant_id}-{uuid4()}", next_question="Cual es el nombre de la empresa y que productos o servicios ofrece?")


@router.post("/sessions/{session_id}/messages", response_model=SetupSessionRead)
def send_setup_message(session_id: str, payload: SetupMessageCreate, tenant: TenantContext = Depends(resolve_tenant)):
    return SetupSessionRead(session_id=session_id, next_question="Que reglas de atencion, tono y criterios de derivacion humana debe respetar el agente?")


@router.post("/sessions/{session_id}/generate-context", response_model=GeneratedContextRead)
def generate_context(session_id: str, tenant: TenantContext = Depends(resolve_tenant)):
    return GeneratedContextRead(summary=f"Contexto estructurado pendiente de revision humana para tenant {tenant.tenant_id}.")
