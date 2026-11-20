from datetime import UTC, datetime

from sqlalchemy import Text, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import text
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.config import get_settings
from app.core.security import generate_ingest_key, generate_tenant_code, hash_secret
from app.core.tenant_resolver import sanitize_schema_name
from app.public_models.migration_registry import MigrationRegistry
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.tenant import TenantProvisionRequest
from app.services.tenant_data import tenant_exec_options
from app.services.tenant_message_schema import upgrade_message_schema
from app import tenant_models


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def apply_optional_schema_grants(db: Session, schema_name: str) -> None:
    role = get_settings().database_grant_role.strip()
    if not role:
        return
    quoted_schema = quote_identifier(schema_name)
    quoted_role = quote_identifier(role)
    try:
        with db.begin_nested():
            db.execute(text(f"GRANT USAGE ON SCHEMA {quoted_schema} TO {quoted_role}"))
            db.execute(text(f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA {quoted_schema} TO {quoted_role}"))
            db.execute(text(f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA {quoted_schema} TO {quoted_role}"))
            db.execute(text(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA {quoted_schema} TO {quoted_role}"))
            db.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT ALL ON TABLES TO {quoted_role}"))
            db.execute(text(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {quoted_schema} GRANT ALL ON SEQUENCES TO {quoted_role}"))
    except SQLAlchemyError:
        # Grants are optional for external readers. Keep tenant provisioning atomic.
        return


def apply_tenant_database_objects(db: Session, schema_name: str) -> None:
    quoted_schema = quote_identifier(schema_name)
    db.execute(
        text(
            f"""
            CREATE OR REPLACE VIEW {quoted_schema}.v_inventario_disponible AS
            SELECT
                id, marca, modelo, anio, version, color, condicion,
                kilometraje, tipo_vehiculo, transmision, combustible, precio_lista
            FROM {quoted_schema}.inventario_vehiculos
            WHERE disponible = TRUE
            ORDER BY marca, modelo, anio DESC, precio_lista ASC
            """
        )
    )
    db.execute(
        text(
            f"""
            CREATE OR REPLACE FUNCTION {quoted_schema}.fn_set_updated_at()
            RETURNS TRIGGER AS $$
            BEGIN
                NEW.actualizado_en = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    for table_name in ("clientes", "leads", "inventario_vehiculos"):
        trigger_name = f"trg_{table_name}_updated_at"
        db.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name} ON {quoted_schema}.{table_name}"))
        db.execute(
            text(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE UPDATE ON {quoted_schema}.{table_name}
                FOR EACH ROW EXECUTE FUNCTION {quoted_schema}.fn_set_updated_at()
                """
            )
        )
    db.execute(
        text(
            f"""
            COMMENT ON TABLE {quoted_schema}.log_limpiezas IS
            'Registro de auditoria de ejecuciones de limpieza y anonimizacion - Ley 21.719'
            """
        )
    )

    db.execute(text(f"""
        CREATE INDEX IF NOT EXISTS idx_messages_thread_id
        ON {quoted_schema}.mensajes_dashboard (whatsapp_id, id)
    """))

    db.execute(
        text(
            f"""
            CREATE OR REPLACE FUNCTION {quoted_schema}.fn_actualizar_resumen_conversacion()
            RETURNS TRIGGER AS $$
            DECLARE
                v_nombre_cliente TEXT;
            BEGIN
                SELECT nombre INTO v_nombre_cliente
                FROM {quoted_schema}.clientes
                WHERE whatsapp_id = NEW.whatsapp_id
                LIMIT 1;

                INSERT INTO {quoted_schema}.conversaciones_resumen
                    (whatsapp_id, nombre_cliente, ultimo_mensaje, ultimo_rol, ultimo_mensaje_en, total_mensajes, no_leidos, actualizado_en)
                VALUES
                    (
                        NEW.whatsapp_id,
                        v_nombre_cliente,
                        NEW.mensaje,
                        NEW.rol,
                        NEW.creado_en,
                        1,
                        CASE WHEN NEW.rol = 'usuario' THEN 1 ELSE 0 END,
                        NOW()
                    )
                ON CONFLICT (whatsapp_id) DO UPDATE SET
                    nombre_cliente    = COALESCE(EXCLUDED.nombre_cliente, {quoted_schema}.conversaciones_resumen.nombre_cliente),
                    ultimo_mensaje    = EXCLUDED.ultimo_mensaje,
                    ultimo_rol        = EXCLUDED.ultimo_rol,
                    ultimo_mensaje_en = EXCLUDED.ultimo_mensaje_en,
                    total_mensajes    = {quoted_schema}.conversaciones_resumen.total_mensajes + 1,
                    no_leidos         = CASE
                                            WHEN NEW.rol = 'usuario'
                                                THEN {quoted_schema}.conversaciones_resumen.no_leidos + 1
                                            ELSE {quoted_schema}.conversaciones_resumen.no_leidos
                                         END,
                    actualizado_en    = NOW();
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )

    db.execute(text(f"DROP TRIGGER IF EXISTS trg_mensaje_actualiza_resumen ON {quoted_schema}.mensajes_dashboard"))
    db.execute(
        text(
            f"""
            CREATE TRIGGER trg_mensaje_actualiza_resumen
            AFTER INSERT ON {quoted_schema}.mensajes_dashboard
            FOR EACH ROW EXECUTE FUNCTION {quoted_schema}.fn_actualizar_resumen_conversacion()
            """
        )
    )

    db.execute(
        text(
            f"""
            CREATE OR REPLACE FUNCTION {quoted_schema}.fn_sincronizar_nombre_cliente_resumen()
            RETURNS TRIGGER AS $$
            BEGIN
                UPDATE {quoted_schema}.conversaciones_resumen
                SET nombre_cliente = NEW.nombre,
                    actualizado_en = NOW()
                WHERE whatsapp_id = NEW.whatsapp_id
                  AND nombre_cliente IS NULL;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )

    db.execute(text(f"DROP TRIGGER IF EXISTS trg_cliente_sincroniza_resumen ON {quoted_schema}.clientes"))
    db.execute(
        text(
            f"""
            CREATE TRIGGER trg_cliente_sincroniza_resumen
            AFTER INSERT ON {quoted_schema}.clientes
            FOR EACH ROW EXECUTE FUNCTION {quoted_schema}.fn_sincronizar_nombre_cliente_resumen()
            """
        )
    )

    apply_optional_schema_grants(db, schema_name)

    db.execute(
        text(
            f"""
            INSERT INTO {quoted_schema}.conversaciones_resumen
                (whatsapp_id, nombre_cliente, ultimo_mensaje, ultimo_rol, ultimo_mensaje_en, total_mensajes, no_leidos, actualizado_en)
            SELECT
                md.whatsapp_id,
                c.nombre                                                AS nombre_cliente,
                (ARRAY_AGG(md.mensaje ORDER BY md.creado_en DESC))[1]  AS ultimo_mensaje,
                (ARRAY_AGG(md.rol ORDER BY md.creado_en DESC))[1]      AS ultimo_rol,
                MAX(md.creado_en)                                       AS ultimo_mensaje_en,
                COUNT(*)                                                AS total_mensajes,
                0                                                        AS no_leidos,
                NOW()                                                    AS actualizado_en
            FROM {quoted_schema}.mensajes_dashboard md
            LEFT JOIN {quoted_schema}.clientes c ON c.whatsapp_id = md.whatsapp_id
            GROUP BY md.whatsapp_id, c.nombre
            ON CONFLICT (whatsapp_id) DO NOTHING
            """
        )
    )


def create_system_event(
    db: Session,
    event_type: str,
    auth_tenant_id: int | None = None,
    schema_name: str | None = None,
    payload: dict | None = None,
) -> None:
    db.add(
        SystemEvent(
            auth_tenant_id=auth_tenant_id,
            schema_name=schema_name,
            event_type=event_type,
            payload=payload or {},
        )
    )


def apply_tenant_schema(db: Session, schema_name: str) -> None:
    # Serialize upgrades of the same schema, including first-time provisioning.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"flowkron-schema:{schema_name}"})
    connection = db.connection()
    connection.execute(CreateSchema(schema_name, if_not_exists=True))
    tenant_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.schema == "tenant" and table.name in tenant_models.ACTIVE_TENANT_TABLE_NAMES
    ]
    tenant_connection = connection.execution_options(**tenant_exec_options(schema_name))
    Base.metadata.create_all(bind=tenant_connection, tables=tenant_tables)
    # Earlier consent updates did not retain the provider timestamp. Preserve
    # the last recorded decision boundary from tenant-scoped audit history.
    audit_client = SystemEvent.payload["client_id"].astext
    latest_consent = select(
        audit_client.label("client_reference"),
        func.max(SystemEvent.created_at).label("recorded_at"),
    ).where(
        SystemEvent.schema_name == schema_name,
        SystemEvent.event_type == "whatsapp.consent.changed",
    ).group_by(audit_client).subquery()
    tenant_connection.execute(insert(tenant_models.WhatsAppConsentState).from_select(
        ["client_id", "decision_at"],
        select(tenant_models.Cliente.id, latest_consent.c.recorded_at).join(
            latest_consent, tenant_models.Cliente.id.cast(Text) == latest_consent.c.client_reference,
        ),
    ).on_conflict_do_nothing())
    upgrade_message_schema(db, schema_name)
    apply_tenant_database_objects(db, schema_name)


def recreate_tenant_schema(db: Session, schema_name: str) -> None:
    connection = db.connection()
    connection.execute(DropSchema(schema_name, cascade=True, if_exists=True))
    apply_tenant_schema(db, schema_name)


def register_migration(db: Session, schema_name: str, status: str, error_message: str | None = None) -> None:
    version = get_settings().tenant_migration_version
    migration = db.scalar(
        select(MigrationRegistry).where(
            MigrationRegistry.schema_name == schema_name,
            MigrationRegistry.migration_version == version,
        )
    )
    if not migration:
        migration = MigrationRegistry(schema_name=schema_name, migration_version=version)
        db.add(migration)
    migration.status = status
    migration.executed_at = datetime.now(UTC)
    migration.error_message = error_message


def _lock_runtime_transition(db: Session, auth_tenant_id: int) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": f"flowkron-runtime:{auth_tenant_id}"})


def provision_tenant(db: Session, request: TenantProvisionRequest) -> tuple[TenantRuntime, str | None, bool]:
    _lock_runtime_transition(db, request.auth_tenant_id)
    existing = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == request.auth_tenant_id).with_for_update())
    if existing:
        # Neither a successful provisioning attempt nor a failed retry may
        # erase suspension. Schema maintenance has separate internal routes.
        if existing.status == "suspended":
            return existing, None, False
        auth_tenant_id = existing.auth_tenant_id
        schema_name = existing.schema_name
        try:
            if request.recreate_schema:
                recreate_tenant_schema(db, schema_name)
                event_type = "tenant.recreated"
            else:
                apply_tenant_schema(db, schema_name)
                event_type = "tenant.reprovisioned"
            existing.status = "active"
            existing.provisioned_at = datetime.now(UTC)
            register_migration(db, schema_name, "success")
            create_system_event(
                db,
                event_type,
                auth_tenant_id,
                schema_name,
                {"recreate_schema": request.recreate_schema},
            )
            db.commit()
            db.refresh(existing)
        except SQLAlchemyError as exc:
            db.rollback()
            existing.status = "provision_failed"
            register_migration(db, schema_name, "failed", str(exc))
            create_system_event(
                db,
                "tenant.reprovision_failed",
                auth_tenant_id,
                schema_name,
                {"error": str(exc), "recreate_schema": request.recreate_schema},
            )
            db.commit()
            raise
        return existing, None, False

    schema_name = sanitize_schema_name(request.tenant_slug)
    base_schema_name = schema_name
    suffix = 1
    while db.scalar(select(TenantRuntime).where(TenantRuntime.schema_name == schema_name)):
        suffix += 1
        schema_name = f"{base_schema_name[:58]}_{suffix}"[:63]

    ingest_key = generate_ingest_key()
    runtime = TenantRuntime(
        auth_tenant_id=request.auth_tenant_id,
        tenant_slug=request.tenant_slug,
        schema_name=schema_name,
        tenant_code=generate_tenant_code(),
        ingest_key_hash=hash_secret(ingest_key),
        plan=request.plan,
        status="pending",
    )
    db.add(runtime)
    db.flush()

    try:
        apply_tenant_schema(db, schema_name)
        runtime.status = "active"
        runtime.provisioned_at = datetime.now(UTC)
        register_migration(db, schema_name, "success")
        create_system_event(
            db,
            "tenant.provisioned",
            request.auth_tenant_id,
            schema_name,
            {"plan": request.plan, "tenant_slug": request.tenant_slug},
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        runtime = TenantRuntime(
            auth_tenant_id=request.auth_tenant_id,
            tenant_slug=request.tenant_slug,
            schema_name=schema_name,
            tenant_code=generate_tenant_code(),
            ingest_key_hash=hash_secret(ingest_key),
            plan=request.plan,
            status="provision_failed",
        )
        db.add(runtime)
        register_migration(db, schema_name, "failed", str(exc))
        create_system_event(db, "tenant.provision_failed", request.auth_tenant_id, schema_name, {"error": str(exc)})
        db.commit()
        raise

    db.refresh(runtime)
    return runtime, ingest_key, True


def set_tenant_status(db: Session, auth_tenant_id: int, status: str) -> TenantRuntime | None:
    _lock_runtime_transition(db, auth_tenant_id)
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == auth_tenant_id))
    if not runtime:
        return None
    runtime.status = status
    runtime.suspended_at = datetime.now(UTC) if status == "suspended" else None
    create_system_event(db, f"tenant.{status}", runtime.auth_tenant_id, runtime.schema_name)
    db.commit()
    db.refresh(runtime)
    return runtime


def rotate_ingest_key(db: Session, auth_tenant_id: int) -> tuple[TenantRuntime | None, str | None]:
    runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.auth_tenant_id == auth_tenant_id))
    if not runtime:
        return None, None
    ingest_key = generate_ingest_key()
    runtime.ingest_key_hash = hash_secret(ingest_key)
    create_system_event(db, "ingest.key.rotated", runtime.auth_tenant_id, runtime.schema_name)
    db.commit()
    db.refresh(runtime)
    return runtime, ingest_key


def migrate_runtime(db: Session, runtime: TenantRuntime) -> dict:
    try:
        apply_tenant_schema(db, runtime.schema_name)
        register_migration(db, runtime.schema_name, "success")
        create_system_event(db, "migration.success", runtime.auth_tenant_id, runtime.schema_name)
        db.commit()
        return {"schema_name": runtime.schema_name, "status": "success"}
    except SQLAlchemyError as exc:
        db.rollback()
        register_migration(db, runtime.schema_name, "failed", str(exc))
        create_system_event(db, "migration.failed", runtime.auth_tenant_id, runtime.schema_name, {"error": str(exc)})
        db.commit()
        return {"schema_name": runtime.schema_name, "status": "failed", "error": str(exc)}


def migrate_all_tenants(db: Session) -> dict:
    runtimes = list(db.scalars(select(TenantRuntime).where(TenantRuntime.status == "active")).all())
    results = [migrate_runtime(db, runtime) for runtime in runtimes]
    success = sum(1 for result in results if result["status"] == "success")
    failed = len(results) - success
    return {"total": len(results), "success": success, "failed": failed, "results": results}
