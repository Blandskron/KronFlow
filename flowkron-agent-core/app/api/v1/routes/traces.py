from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.tenant import TenantContext, resolve_tenant
from app.models.agent import AgentResponseTrace
from app.models.conversation import ConversationSession, RetrievalTrace

router = APIRouter(prefix="/api/v1/agent", tags=["Traces"])


def require_local_persistence() -> None:
    if get_settings().persistence_mode == "operational":
        raise HTTPException(status_code=501, detail="Trace persistence is delegated to flowkron-operational-service.")


@router.get("/traces/{trace_id}")
def get_trace(trace_id: int, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    trace = db.get(AgentResponseTrace, trace_id)
    if not trace or trace.tenant_id != tenant.tenant_id:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"id": trace.id, "conversation_id": trace.conversation_id, "confidence": trace.confidence, "sources": trace.sources}


@router.get("/conversations/{conversation_id}/traces")
def get_conversation_traces(conversation_id: str, tenant: TenantContext = Depends(resolve_tenant), db: Session = Depends(get_db)):
    require_local_persistence()
    conversation = db.scalar(select(ConversationSession).where(ConversationSession.tenant_id == tenant.tenant_id, ConversationSession.external_conversation_id == conversation_id))
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    traces = db.scalars(select(RetrievalTrace).where(RetrievalTrace.tenant_id == tenant.tenant_id, RetrievalTrace.conversation_id == conversation.id).order_by(RetrievalTrace.id)).all()
    return [{"id": trace.id, "query": trace.query, "confidence": trace.confidence, "sources": trace.sources} for trace in traces]
