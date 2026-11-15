from datetime import datetime

from pydantic import BaseModel, Field


class TenantProvisionRequest(BaseModel):
    auth_tenant_id: int = Field(gt=0)
    tenant_slug: str = Field(min_length=1, max_length=120)
    tenant_name: str | None = Field(default=None, max_length=180)
    plan: str = Field(default="starter", max_length=32)
    recreate_schema: bool = False


class TenantRuntimeResponse(BaseModel):
    id: int
    auth_tenant_id: int
    tenant_slug: str
    schema_name: str
    tenant_code: str
    plan: str
    status: str
    provisioned_at: datetime | None
    suspended_at: datetime | None

    model_config = {"from_attributes": True}


class TenantProvisionResponse(BaseModel):
    runtime: TenantRuntimeResponse
    ingest_key: str | None = None
    created: bool


class RotateIngestKeyResponse(BaseModel):
    tenant_code: str
    ingest_key: str


class MigrateAllResponse(BaseModel):
    total: int
    success: int
    failed: int
    results: list[dict]

