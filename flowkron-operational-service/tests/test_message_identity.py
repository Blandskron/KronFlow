"""FK-01 integration tests against an owned, disposable PostgreSQL cluster.

Opt in with FLOWKRON_TEST_POSTGRES_BIN pointing to installed PostgreSQL binaries.
Never reads DATABASE_URL or connects to an existing cluster. No extra dependency.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import public_models  # noqa: F401
from app.core.database import Base
from app.core.tenant_resolver import TenantContext
from app.schemas.conversation import MessageOut
from app.schemas.ingest import WhatsAppMessageIn
from app.services.conversation_service import list_messages
from app.services.ingest_service import ingest_whatsapp_message
from app.services.tenant_data import message_to_dict, tenant_exec_options
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.operations import Cliente, Conversation, Lead, Message


class MessageInputTests(unittest.TestCase):
    def test_old_payload_and_reserved_connection(self):
        payload = WhatsAppMessageIn(external_message_id="old-client", phone="12025550138", sent_at=datetime.now(timezone.utc))
        self.assertEqual(payload.connection_id, "default")
        self.assertIsNone(payload.provider_message_id)
        for changes in ({"connection_id": "second"}, {"message_type": "image"}, {"delivery_status": "read"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                WhatsAppMessageIn(**(payload.model_dump() | changes))


@unittest.skipUnless(os.getenv("FLOWKRON_TEST_POSTGRES_BIN"), "Set FLOWKRON_TEST_POSTGRES_BIN for disposable PostgreSQL tests")
class MessageIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="flowkron-fk01-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.bin = Path(os.environ["FLOWKRON_TEST_POSTGRES_BIN"]).resolve()
        cls.data = cls.root / "data"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        cls.pg("initdb", "-D", str(cls.data), "-U", "fk01", "-A", "trust", "--encoding=UTF8", "--no-locale")
        cls.addClassCleanup(lambda: cls.pg("pg_ctl", "-D", str(cls.data), "-m", "fast", "-w", "stop"))
        cls.pg("pg_ctl", "-D", str(cls.data), "-l", str(cls.root / "postgres.log"),
               "-o", f"-h 127.0.0.1 -p {port}", "-w", "start")
        cls.engine = create_engine(f"postgresql+psycopg://fk01@127.0.0.1:{port}/postgres")
        cls.addClassCleanup(cls.engine.dispose)
        Base.metadata.create_all(cls.engine, tables=[table for table in Base.metadata.sorted_tables if table.schema in (None, "public")])

    @classmethod
    def pg(cls, executable, *args):
        suffix = ".exe" if os.name == "nt" else ""
        # A PostgreSQL child can inherit captured pipe handles on Windows and
        # keep communicate() waiting after pg_ctl exits. Use a private log file.
        log = cls.root / "commands.log"
        with log.open("a", encoding="utf-8") as output:
            result = subprocess.run([str(cls.bin / (executable + suffix)), *args], stdout=output,
                                    stderr=subprocess.STDOUT, timeout=60,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(f"{executable}: {log.read_text(encoding='utf-8', errors='replace')}")

    def tenant(self):
        schema = "tenant_fk01_" + uuid4().hex[:12]
        with Session(self.engine) as db:
            apply_tenant_schema(db, schema)
            db.commit()
        return TenantContext(auth_tenant_id=1, tenant_slug=schema, schema_name=schema,
                             tenant_code=schema, plan="free", status="active")

    def payload(self, **changes):
        return WhatsAppMessageIn(**({"external_message_id": "external-1", "phone": "12025550138",
                                     "provider_message_id": "provider-1", "body": "Consulta sintética",
                                     "sent_at": datetime(2026, 1, 1, tzinfo=timezone.utc)} | changes))

    def ingest(self, tenant, payload):
        with Session(self.engine) as db:
            return ingest_whatsapp_message(db, tenant, payload)

    def test_new_tenant_persists_identity_and_preserves_response_shape(self):
        tenant = self.tenant()
        result = self.ingest(tenant, self.payload())
        with Session(self.engine) as db:
            messages, total = list_messages(db, tenant, result["conversation_id"], 50, 0)
        self.assertEqual(total, 1)
        message = MessageOut(**messages[0])
        self.assertEqual(message.external_message_id, "external-1")
        self.assertEqual(message.provider_message_id, "provider-1")
        self.assertEqual(message.direction, "inbound")
        self.assertEqual(message.delivery_status, "received")
        self.assertGreater(message.recorded_at, message.sent_at)
        self.assertEqual(message.created_at, message.sent_at)  # existing API semantics

    def test_duplicate_is_read_only_and_returns_original_message(self):
        tenant = self.tenant()
        first = self.ingest(tenant, self.payload(full_name="Original"))
        repeated = self.ingest(tenant, self.payload(full_name="Changed", body="Changed"))
        self.assertTrue(repeated["duplicate"])
        self.assertEqual(first["message_id"], repeated["message_id"])
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(Cliente.nombre)), "Original")
            self.assertEqual(db.scalar(select(Conversation.message))["body"], "Consulta sintética")
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 1)
        with self.assertRaises(HTTPException) as error:
            self.ingest(tenant, self.payload(external_thread_id="different-thread"))
        self.assertEqual(error.exception.status_code, 409)

    def test_concurrent_duplicates_create_one_message_contact_lead_and_summary(self):
        tenant = self.tenant()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.ingest(tenant, self.payload()), range(16)))
        self.assertEqual(sum(not result["duplicate"] for result in results), 1)
        self.assertEqual(len({result["message_id"] for result in results}), 1)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            for model in (Message, Cliente, Conversation, Lead):
                self.assertEqual(db.scalar(select(func.count()).select_from(model)), 1)
            self.assertEqual(db.scalar(text(f'SELECT total_mensajes FROM "{tenant.schema_name}".conversaciones_resumen')), 1)

    def test_different_messages_same_contact_are_serialized_without_losing_turns(self):
        tenant = self.tenant()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda index: self.ingest(tenant, self.payload(external_message_id=f"external-{index}")), range(12)))
        self.assertTrue(all(not result["duplicate"] for result in results))
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 12)
            self.assertEqual(db.scalar(select(func.count()).select_from(Lead)), 1)

    def test_tenant_isolation_and_database_uniqueness(self):
        first, second = self.tenant(), self.tenant()
        self.ingest(first, self.payload())
        result = self.ingest(second, self.payload())
        self.assertFalse(result["duplicate"])
        with Session(self.engine.execution_options(**tenant_exec_options(first.schema_name))) as db:
            db.add(Message(whatsapp_id="12025550138", rol="usuario", direction="inbound", mensaje="duplicate",
                           connection_id="default", channel="whatsapp", external_message_id="external-1"))
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_outbound_uses_its_own_provider_id_and_does_not_assume_delivery(self):
        tenant = self.tenant()
        first = self.ingest(tenant, self.payload(direction="outbound", provider_message_id="outbound-provider"))
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            message = db.get(Message, first["message_id"])
            self.assertEqual(message.provider_message_id, "outbound-provider")
            self.assertEqual(message.delivery_status, "unknown")

    def test_existing_schema_upgrade_is_repeatable_and_preserves_legacy_history(self):
        schema = "tenant_fk01_" + uuid4().hex[:12]
        with Session(self.engine) as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
            db.execute(text(f'''CREATE TABLE "{schema}".mensajes_dashboard (
                id bigserial PRIMARY KEY, whatsapp_id text NOT NULL, rol text NOT NULL,
                mensaje text NOT NULL, creado_en timestamptz NOT NULL DEFAULT now())'''))
            db.execute(text(f'''INSERT INTO "{schema}".mensajes_dashboard (whatsapp_id, rol, mensaje)
                VALUES ('12025550138', 'usuario', 'historial usuario'), ('12025550138', 'agente', 'historial agente')'''))
            db.commit()
            for _ in range(2):
                apply_tenant_schema(db, schema)
                db.commit()
            rows = db.execute(text(f'SELECT * FROM "{schema}".mensajes_dashboard ORDER BY id')).mappings().all()
            self.assertEqual([row["direction"] for row in rows], ["inbound", "outbound"])
            self.assertEqual([row["mensaje"] for row in rows], ["historial usuario", "historial agente"])
            self.assertTrue(all(row["external_message_id"] is None and row["provider_message_id"] is None for row in rows))
            self.assertTrue(all(row["recorded_at"] == row["creado_en"] for row in rows))
            self.assertEqual(db.scalar(text(f'SELECT total_mensajes FROM "{schema}".conversaciones_resumen')), 2)
            # Application rollback / old SQL writers remain valid.
            db.execute(text(f'''INSERT INTO "{schema}".mensajes_dashboard (whatsapp_id, rol, mensaje)
                VALUES ('12025550138', 'agente', 'escritor anterior')'''))
            self.assertEqual(db.scalar(text(f'SELECT direction FROM "{schema}".mensajes_dashboard WHERE id=3')), "outbound")
            db.execute(text(f'''INSERT INTO "{schema}".mensajes_procesados (message_id) VALUES ('legacy-marker')'''))
            db.commit()
        tenant = TenantContext(1, schema, schema, schema, "free", "active")
        repeated = self.ingest(tenant, self.payload(external_message_id="legacy-marker"))
        self.assertTrue(repeated["duplicate"])
        self.assertIsNone(repeated["message_id"])
        with Session(self.engine.execution_options(**tenant_exec_options(schema))) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 3)
            legacy = MessageOut(**message_to_dict(db.get(Message, 1)))
            self.assertEqual(legacy.external_message_id, "1")
            self.assertIsNone(legacy.provider_message_id)
            self.assertEqual(legacy.delivery_status, "unknown")

    def test_failed_upgrade_rolls_back_without_changing_old_rows(self):
        schema = "tenant_fk01_" + uuid4().hex[:12]
        with Session(self.engine) as db:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
            db.execute(text(f'''CREATE TABLE "{schema}".mensajes_dashboard (
                id bigserial PRIMARY KEY, whatsapp_id text NOT NULL, rol text NOT NULL,
                mensaje text NOT NULL, creado_en timestamptz NOT NULL DEFAULT now())'''))
            db.execute(text(f'''INSERT INTO "{schema}".mensajes_dashboard (whatsapp_id, rol, mensaje)
                VALUES ('12025550138', 'usuario', 'preservado')'''))
            db.commit()
            apply_tenant_schema(db, schema)
            db.rollback()  # simulate a later failing step in the same migration
            self.assertEqual(db.scalar(text(f'SELECT mensaje FROM "{schema}".mensajes_dashboard')), "preservado")
            self.assertEqual(db.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema=:schema AND table_name='mensajes_dashboard' AND column_name='provider_message_id'"), {"schema": schema}), 0)
