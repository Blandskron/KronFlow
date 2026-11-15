from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.routes.agent import router as agent_router
from app.api.v1.routes.context import router as context_router
from app.api.v1.routes.rules import router as rules_router
from app.api.v1.routes.setup import router as setup_router
from app.api.v1.routes.traces import router as traces_router
from app.core.config import get_settings
from app.core.contracts import api_contract_middleware, http_exception_handler, validation_exception_handler
from app.core.database import check_database, create_tables
from app.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.allow_local_db_bootstrap:
        create_tables()
    yield


settings = get_settings()
configure_logging()
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

app.include_router(context_router)
app.include_router(setup_router)
app.include_router(agent_router)
app.include_router(rules_router)
app.include_router(traces_router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "flowkron-agent-core"}


@app.get("/healthz", tags=["Health"])
def healthz():
    return health()


@app.get("/ready", tags=["Health"])
def ready():
    if settings.persistence_mode == "operational":
        return {"status": "ready", "persistence": "delegated", "operational_service_url": settings.operational_service_url}
    return {"status": "ready" if check_database() else "not_ready"}
