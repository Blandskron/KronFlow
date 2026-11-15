from sqlalchemy import text

from app.core.database import SessionLocal
from app.tenant_models import ACTIVE_TENANT_TABLE_NAMES
from app.services.tenant_provisioning_service import apply_tenant_schema


def main() -> None:
    schema_name = "tenant_validation_tmp"
    db = SessionLocal()
    try:
        apply_tenant_schema(db, schema_name)
        tables = db.execute(
            text("select table_name from information_schema.tables where table_schema=:schema_name and table_type='BASE TABLE' order by table_name"),
            {"schema_name": schema_name},
        ).scalars().all()
        expected_tables = sorted(ACTIVE_TENANT_TABLE_NAMES)
        if tables != expected_tables:
            raise SystemExit({"expected_tables": expected_tables, "actual_tables": tables})
        views = db.execute(
            text("select table_name from information_schema.views where table_schema=:schema_name order by table_name"),
            {"schema_name": schema_name},
        ).scalars().all()
        triggers = db.execute(
            text("select trigger_name from information_schema.triggers where trigger_schema=:schema_name order by trigger_name"),
            {"schema_name": schema_name},
        ).scalars().all()
        print({"tables": tables, "views": views, "triggers": triggers})
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
