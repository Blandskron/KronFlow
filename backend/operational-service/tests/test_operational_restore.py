import os
import subprocess
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.public_models.erasure_tombstone import PrivacyErasureTombstone
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.ingest import ConsentIn
from app.schemas.privacy_case import PrivacyCaseCreateIn
from app.services.conversation_service import list_messages
from app.services.ingest_service import get_consent, ingest_whatsapp_message, save_consent
from app.services.privacy_case_service import (
    create_privacy_case,
    execute_privacy_erasure,
    reapply_erasure_tombstones,
)
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente, Lead, Message
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

    def test_restore_reapplies_erasure_tombstones_with_zero_pii_resurrection(self):
        """FK-15 / PRV-028: encrypted backup taken before /erase never resurrects PII after tombstone reconciliation."""
        tenant = self.tenant()
        phone = "12025550199"
        payload = self.payload(phone=phone, full_name="Synthetic Erasure Subject")
        self.ingest(tenant, payload)

        # 1. Take encrypted backup BEFORE DSAR erasure
        source = self.engine.url.set(drivername="postgresql")
        target = source.set(database="fk15_tombstone_restore")
        cipher = Fernet(Fernet.generate_key())
        dump = self.postgres_client("pg_dump", "--format=custom", "--dbname", source.render_as_string())
        encrypted_archive = cipher.encrypt(dump)

        # 2. Execute DSAR erasure after backup (creates public.privacy_erasure_tombstones)
        with Session(self.engine) as db:
            case = create_privacy_case(
                db,
                tenant,
                PrivacyCaseCreateIn(kind="eliminacion", whatsapp_id=phone),
                actor_id="dpo-drill",
            )
            execute_privacy_erasure(db, tenant, case["id"], actor_id="dpo-drill", confirmed=True)
            tombstones = list(db.scalars(select(PrivacyErasureTombstone)).all())
            self.assertGreaterEqual(len(tombstones), 1)
            exported_tombstones = [
                {
                    "auth_tenant_id": t.auth_tenant_id,
                    "schema_name": t.schema_name,
                    "identifier_kind": t.identifier_kind,
                    "subject_hash": t.subject_hash,
                    "case_id": t.case_id,
                    "erased_at": t.erased_at,
                }
                for t in tombstones
            ]

        # 3. Restore pre-erasure encrypted backup into fresh DB and measure RTO
        started = time.monotonic()
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(text("CREATE DATABASE fk15_tombstone_restore"))
        self.postgres_client(
            "pg_restore",
            "--exit-on-error",
            "--single-transaction",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            target.render_as_string(),
            data=cipher.decrypt(encrypted_archive),
        )
        rto_seconds = time.monotonic() - started
        self.assertGreaterEqual(rto_seconds, 0.0)

        restored = create_engine(target.set(drivername="postgresql+psycopg"))
        self.addCleanup(restored.dispose)

        # 4. Replay post-backup tombstone ledger and run reconciliation
        with Session(restored) as db:
            for item in exported_tombstones:
                db.add(PrivacyErasureTombstone(**item))
            db.commit()
            summary = reapply_erasure_tombstones(db, schema_name=tenant.schema_name)
            self.assertEqual(summary["reapplied_clients"], 1)
            self.assertGreaterEqual(summary["reapplied_messages"], 1)

        # 5. Assert zero PII resurrected in restored tenant schema
        with Session(restored.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            clients = list(db.scalars(select(Cliente)).all())
            self.assertEqual(len(clients), 1)
            self.assertEqual(clients[0].nombre, "Anonimizado")
            self.assertIsNone(clients[0].email)
            self.assertIsNone(clients[0].telefono)
            self.assertTrue((clients[0].whatsapp_id or "").startswith("anon:"))

            messages = list(db.scalars(select(Message)).all())
            self.assertGreaterEqual(len(messages), 1)
            for msg in messages:
                self.assertEqual(msg.mensaje, "[REDACTED_PRIVACY]")
                self.assertTrue((msg.whatsapp_id or "").startswith("anon:"))
