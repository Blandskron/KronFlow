from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.tenant_provisioning_service import apply_tenant_schema


def main() -> None:
    schema_name = "tenant_seed_validation_tmp"
    seed_path = Path(__file__).with_name("seed_demo_tenant.sql")
    seed_sql = seed_path.read_text(encoding="utf-8").replace("SET search_path TO tenant_flowkron_demo;", f"SET search_path TO {schema_name};")

    db = SessionLocal()
    try:
        db.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
        apply_tenant_schema(db, schema_name)
        db.connection().exec_driver_sql(seed_sql)
        counts = {}
        for table_name in (
            "clientes",
            "leads",
            "inventario_vehiculos",
            "conversaciones",
            "mensajes_dashboard",
            "conversaciones_resumen",
            "mensajes_procesados",
            "solicitudes_derechos",
            "log_limpiezas",
            "ejecutivos",
            "reglas_negocio",
            "rate_limit",
        ):
            counts[table_name] = db.execute(text(f'SELECT COUNT(*) FROM "{schema_name}".{table_name}')).scalar_one()
        print(counts)
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    main()
