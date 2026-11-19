"""Additive FK-01 upgrade of the active message store; safe to run again.

Historical external/provider IDs cannot be reconstructed from processed markers.
Never infer a correspondence from insertion order or phone alone.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.tenant_resolver import quote_identifier


def upgrade_message_schema(db: Session, schema_name: str) -> None:
    table = f"{quote_identifier(schema_name)}.mensajes_dashboard"
    db.execute(text(f"""
        ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS connection_id varchar(80) NOT NULL DEFAULT 'default',
            ADD COLUMN IF NOT EXISTS channel varchar(32) NOT NULL DEFAULT 'whatsapp',
            ADD COLUMN IF NOT EXISTS external_message_id varchar(220),
            ADD COLUMN IF NOT EXISTS provider_message_id varchar(220),
            ADD COLUMN IF NOT EXISTS direction varchar(16),
            ADD COLUMN IF NOT EXISTS message_type varchar(32) NOT NULL DEFAULT 'text',
            ADD COLUMN IF NOT EXISTS delivery_status varchar(16) NOT NULL DEFAULT 'unknown',
            ADD COLUMN IF NOT EXISTS recorded_at timestamptz
    """))
    db.execute(text(f"""
        UPDATE {table} SET direction = CASE WHEN rol = 'usuario' THEN 'inbound' ELSE 'outbound' END
        WHERE direction IS NULL
    """))
    db.execute(text(f"UPDATE {table} SET recorded_at = creado_en WHERE recorded_at IS NULL"))
    # Older writers and SQL seeds only supply rol. Keep those inserts valid
    # during a rolling deployment or an application-only rollback.
    schema = quote_identifier(schema_name)
    db.execute(text(f"""
        CREATE OR REPLACE FUNCTION {schema}.fn_message_direction() RETURNS TRIGGER AS $$
        BEGIN
            IF NEW.direction IS NULL THEN
                NEW.direction := CASE WHEN NEW.rol = 'usuario' THEN 'inbound' ELSE 'outbound' END;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))
    db.execute(text(f"DROP TRIGGER IF EXISTS trg_message_direction ON {table}"))
    db.execute(text(f"""CREATE TRIGGER trg_message_direction BEFORE INSERT ON {table}
        FOR EACH ROW EXECUTE FUNCTION {schema}.fn_message_direction()"""))
    db.execute(text(f"""
        ALTER TABLE {table}
            ALTER COLUMN direction SET NOT NULL,
            ALTER COLUMN recorded_at SET DEFAULT now(),
            ALTER COLUMN recorded_at SET NOT NULL
    """))
    # Constraints cannot use ADD ... IF NOT EXISTS. Query the catalog by table,
    # not just by name: every tenant has its own constraints.
    constraints = {
        "ck_message_direction": "direction IN ('inbound', 'outbound')",
        "ck_message_delivery_status": "delivery_status IN ('unknown', 'received', 'sent', 'delivered', 'read', 'failed')",
    }
    for name, expression in constraints.items():
        exists = db.scalar(text("SELECT 1 FROM pg_constraint WHERE conrelid = to_regclass(:table) AND conname = :name"),
                           {"table": table, "name": name})
        if not exists:
            db.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT "{name}" CHECK ({expression})'))
    db.execute(text(f"""CREATE UNIQUE INDEX IF NOT EXISTS uq_message_external_identity
        ON {table} (connection_id, channel, external_message_id)"""))
    db.execute(text(f"""CREATE INDEX IF NOT EXISTS idx_message_provider_identity
        ON {table} (connection_id, channel, provider_message_id)"""))
