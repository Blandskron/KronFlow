import argparse

from app.core.database import SessionLocal, create_public_tables
from app.schemas.tenant import TenantProvisionRequest
from app.services.tenant_provisioning_service import provision_tenant


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth-tenant-id", type=int, default=1)
    parser.add_argument("--tenant-slug", default="demo-tenant")
    parser.add_argument("--plan", default="starter")
    args = parser.parse_args()

    create_public_tables()
    with SessionLocal() as db:
        runtime, ingest_key, created = provision_tenant(
            db,
            TenantProvisionRequest(
                auth_tenant_id=args.auth_tenant_id,
                tenant_slug=args.tenant_slug,
                plan=args.plan,
            ),
        )
        print(
            {
                "created": created,
                "auth_tenant_id": runtime.auth_tenant_id,
                "schema_name": runtime.schema_name,
                "tenant_code": runtime.tenant_code,
                "ingest_key": ingest_key,
            }
        )


if __name__ == "__main__":
    main()

