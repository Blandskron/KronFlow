import os
import subprocess
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.ingest import ConsentIn
from app.services.conversation_service import list_messages
from app.services.ingest_service import get_consent, ingest_whatsapp_message, save_consent
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente, Lead
from test_message_identity import PostgresCase


class OperationalRestoreTests(PostgresCase):
    def postgres_client(self, executable: str, *args: str, data: bytes | None = None) -> bytes:
        suffix = ".exe" if os.name == "nt" else ""
        return subprocess.run(
            [str(self.bin / (executable + suffix)), *args], capture_output=True, input=data,
            timeout=60, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout

    def test_restore_preserves_schema_isolation_references_consent_and_message_identity(self):
        first, second = self.tenant(), self.tenant()
        phone = "12025550138"
        payloads = [self.payload(phone=phone, full_name=name) for name in ("Synthetic A", "Synthetic B")]
        ingested = [self.ingest(tenant, payload) for tenant, payload in zip((first, second), payloads)]
        with Session(self.engine) as db:
            for tenant_id, tenant in ((11, first), (12, second)):
                db.add(TenantRuntime(auth_tenant_id=tenant_id, schema_name=tenant.schema_name,
                                     tenant_slug=tenant.tenant_slug, tenant_code=tenant.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            db.commit()
            save_consent(db, first, ConsentIn(phone=phone, accepted=True))
            save_consent(db, first, ConsentIn(phone=phone, accepted=False))
            save_consent(db, second, ConsentIn(phone=phone, accepted=True))

        archive = self.root / "operational.dump.fernet"
        source = self.engine.url.set(drivername="postgresql")
        target = source.set(database="fk15_restore")
        cipher = Fernet(Fernet.generate_key())
        dump = self.postgres_client("pg_dump", "--format=custom", "--dbname", source.render_as_string())
        archive.write_bytes(cipher.encrypt(dump))
        token = archive.read_bytes()
        with self.assertRaises(InvalidToken):
            Fernet(Fernet.generate_key()).decrypt(token)
        corrupted = bytearray(urlsafe_b64decode(token))
        corrupted[len(corrupted) // 2] ^= 1
        with self.assertRaises(InvalidToken):
            cipher.decrypt(urlsafe_b64encode(corrupted))
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("CREATE DATABASE fk15_restore"))
        self.postgres_client("pg_restore", "--exit-on-error", "--single-transaction", "--no-owner", "--no-privileges",
                             "--dbname", target.render_as_string(), data=cipher.decrypt(token))

        restored = create_engine(target.set(drivername="postgresql+psycopg"))
        self.addCleanup(restored.dispose)
        with Session(restored) as db:
            runtimes = db.execute(select(TenantRuntime.auth_tenant_id, TenantRuntime.schema_name)).all()
            self.assertCountEqual(runtimes, [(11, first.schema_name), (12, second.schema_name)])
        for tenant, payload, initial, allowed in zip((first, second), payloads, ingested, (False, True)):
            with self.subTest(tenant=tenant.schema_name):
                with Session(restored) as db:
                    messages, total = list_messages(db, tenant, initial["conversation_id"], 25, 0)
                    self.assertEqual(total, 1)
                    self.assertEqual(messages[0]["provider_message_id"], payload.provider_message_id)
                    self.assertEqual(get_consent(db, tenant, phone)["consentimiento_datos"], allowed)
                    duplicate = ingest_whatsapp_message(db, tenant, payload)
                    self.assertTrue(duplicate["duplicate"])
                    self.assertEqual(duplicate["message_id"], initial["message_id"])
                with Session(restored.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
                    self.assertEqual(db.execute(select(Cliente.nombre).join(Lead, Lead.cliente_id == Cliente.id)).all(),
                                     [(payload.full_name,)])

        with Session(restored) as db:
            inserted = ingest_whatsapp_message(db, second, self.payload(
                phone=phone, external_message_id="after-restore", provider_message_id="provider-after-restore",
            ))
            self.assertGreater(inserted["message_id"], ingested[1]["message_id"])
