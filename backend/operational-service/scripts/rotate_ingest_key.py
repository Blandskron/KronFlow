import argparse

from app.core.database import SessionLocal
from app.services.tenant_provisioning_service import rotate_ingest_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("auth_tenant_id", type=int)
    args = parser.parse_args()

    with SessionLocal() as db:
        runtime, ingest_key = rotate_ingest_key(db, args.auth_tenant_id)
        if not runtime or not ingest_key:
            raise SystemExit("Tenant runtime not found")
        print({"tenant_code": runtime.tenant_code, "ingest_key": ingest_key})


if __name__ == "__main__":
    main()

