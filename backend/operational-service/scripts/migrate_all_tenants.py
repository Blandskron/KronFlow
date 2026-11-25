from app.core.database import SessionLocal, create_public_tables
from app.services.tenant_provisioning_service import migrate_all_tenants


def main() -> None:
    create_public_tables()
    with SessionLocal() as db:
        result = migrate_all_tenants(db)
    print(result)


if __name__ == "__main__":
    main()

