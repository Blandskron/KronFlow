from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.ingest.whatsapp import router as whatsapp_ingest_router
from app.api.internal.context import router as internal_context_router
from app.api.internal.migrations import router as internal_migrations_router
from app.api.internal.tenants import router as internal_tenants_router
from app.api.v1.agents import router as agents_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.leads import router as leads_router
from app.api.v1.operational import router as operational_router
from app.core.config import get_settings
from app.core.contracts import api_contract_middleware, http_exception_handler, validation_exception_handler
from app.core.database import check_database, create_public_tables


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_public_tables()
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

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
app.include_router(conversations_router)
app.include_router(analytics_router)
app.include_router(agents_router)
app.include_router(operational_router)


@app.get("/healthz", tags=["Health"])
def healthz():
    return {"status": "ok"}


@app.get("/health", tags=["Health"])
def health():
    return healthz()


@app.get("/readyz", tags=["Health"])
def readyz():
    return {"status": "ready" if check_database() else "not_ready"}

