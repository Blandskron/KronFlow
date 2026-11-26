from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.api.ingest.whatsapp import router as whatsapp_ingest_router
from app.api.internal.context import router as internal_context_router
from app.api.internal.migrations import router as internal_migrations_router
from app.api.internal.tenants import router as internal_tenants_router
from app.api.v1.agents import router as agents_router
from app.api.v1.ai_extensions import router as ai_extensions_router
from app.api.v1.ai_proposals import router as ai_proposals_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.capture import router as capture_router
from app.api.v1.commerce import router as commerce_router
from app.api.v1.contacts import router as contacts_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.domain_events import router as domain_events_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.leads import router as leads_router
from app.api.v1.mcp import router as mcp_router
from app.api.v1.mcp_clients import router as mcp_clients_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.operational import router as operational_router
from app.api.v1.post_v1 import router as post_v1_router
from app.api.v1.tools import router as tools_router
from app.api.v1.voice import router as voice_router
from app.api.v1.webchat import router as webchat_router
from app.api.v1.workflows import router as workflows_router
from app.core.config import get_settings
from app.core.admission import IngestAdmissionMiddleware
from app.core.contracts import api_contract_middleware, http_exception_handler, validation_exception_handler
from app.core.database import check_database, create_public_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_public_tables()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(IngestAdmissionMiddleware)
app.middleware("http")(api_contract_middleware)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(internal_tenants_router)
app.include_router(internal_migrations_router)
app.include_router(internal_context_router)
app.include_router(whatsapp_ingest_router)
app.include_router(leads_router)
app.include_router(opportunities_router)
app.include_router(contacts_router)
app.include_router(conversations_router)
app.include_router(analytics_router)
app.include_router(campaigns_router)
app.include_router(capture_router)
app.include_router(domain_events_router)
app.include_router(agents_router)
app.include_router(ai_extensions_router)
app.include_router(ai_proposals_router)
app.include_router(post_v1_router)
app.include_router(integrations_router)
app.include_router(mcp_router)
app.include_router(mcp_clients_router)
app.include_router(commerce_router)
app.include_router(voice_router)
app.include_router(tools_router)
app.include_router(webchat_router)
app.include_router(workflows_router)
app.include_router(operational_router)


@app.get("/healthz", tags=["Health"])
def healthz():
    return {"status": "ok"}


@app.get("/health", tags=["Health"])
def health():
    return healthz()


@app.get("/readyz", tags=["Health"])
def readyz():
    try:
        if check_database():
            return {"status": "ready"}
    except (SQLAlchemyError, OSError):
        pass
    raise HTTPException(status_code=503, detail="Database unavailable")

