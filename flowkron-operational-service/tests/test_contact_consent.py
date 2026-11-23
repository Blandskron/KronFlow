from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.ingest import ConsentIn
from app.services.ingest_service import save_consent
from app.services.contact_consent_service import read_contact_consent
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente
from app.tenant_models.whatsapp_consent import WhatsAppConsentState
from test_message_identity import PostgresCase
import test_turn_recovery


class ContactConsentTests(PostgresCase):
    def test_manual_fixture_is_repeatable_and_paginates(self):
        tenant = self.tenant()
        with Session(self.engine) as db:
            db.add(TenantRuntime(auth_tenant_id=tenant.auth_tenant_id, schema_name=tenant.schema_name,
                                 tenant_slug=tenant.tenant_slug, tenant_code=tenant.tenant_code,
                                 ingest_key_hash="unused", status="active", plan="free"))
            db.commit()
        fixture = Path(__file__).with_name("fixtures") / "manual_whatsapp_consent_qa.sql"
        for _ in range(2):
            self.pg("psql", "-h", "127.0.0.1", "-p", str(self.engine.url.port), "-U", "fk01", "-d", "postgres",
                    "-X", "-v", "ON_ERROR_STOP=1", "-v", "operational_schema=public",
                    "-v", f"tenant_schema={tenant.schema_name}", "-f", str(fixture))
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            contact_id = db.scalar(select(Cliente.id).where(Cliente.rut == "qa:whatsapp-consent"))
            page = read_contact_consent(db, tenant, contact_id, 15, None)
            self.assertEqual(page.state, "granted")
            self.assertEqual(len(page.items), 15)
            self.assertEqual(page.items[0].kind, "prior_withdrawal")
            self.assertTrue(all(event.effective_at is not None for event in page.items))
            self.assertLess(page.items[0].effective_at, page.decision_at)
            older = read_contact_consent(db, tenant, contact_id, 15, page.next_before_id)
            self.assertEqual(older.state, page.state)
            self.assertEqual(len(older.items), 1)
            self.assertIsNone(older.next_before_id)

    def test_consultation_preserves_current_state_when_reading_an_earlier_withdrawal(self):
        tenant = replace(self.tenant(), auth_tenant_id=811)
        other = replace(self.tenant(), auth_tenant_id=812)
        phone = "12025550138"

        def decision(minute, accepted):
            payload = ConsentIn(phone=phone, accepted=accepted, external_message_id=f"decision-{minute}",
                                sent_at=datetime(2026, 1, 1, 12, minute, tzinfo=timezone.utc))
            with Session(self.engine) as db:
                return save_consent(db, tenant, payload)

        for minute, accepted in ((0, True), (3, True), (2, False)):
            self.assertEqual(decision(minute, accepted)["stale"], minute == 2)
        self.assertTrue(decision(2, False)["duplicate"])

        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            contact = db.scalar(select(Cliente).where(Cliente.whatsapp_id == phone))
            manual = Cliente(rut="crm:manual-qa", nombre="Manual QA", telefono=phone, canal_origen="crm_manual")
            unknown = Cliente(rut="crm:unknown-qa", nombre="WhatsApp QA", whatsapp_id="12025550139")
            db.add_all([manual, unknown])
            db.flush()
            contact_id, manual_id, unknown_id = contact.id, manual.id, unknown.id
            for workspace in (tenant, other):
                db.add(TenantRuntime(auth_tenant_id=workspace.auth_tenant_id, schema_name=workspace.schema_name,
                                     tenant_slug=workspace.tenant_slug, tenant_code=workspace.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            db.add_all([
                SystemEvent(auth_tenant_id=auth_id, schema_name=schema, event_type="whatsapp.consent.changed",
                            payload={"client_id": contact_id, "accepted": False})
                for auth_id, schema in ((812, tenant.schema_name), (811, other.schema_name))
            ])
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        permissions = ["crm.manage"]
        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)

        def http(contact, query=""):
            return test_turn_recovery.TurnRecoveryTests.http(
                self, "GET", f"/api/v1/contacts/{contact}/whatsapp-consent{query}", headers={"X-Tenant-ID": "812"},
            )

        self.assertEqual(http(contact_id)[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "synthetic-actor", 811, None, [], permissions, {}, {},
        )
        self.assertEqual(http(contact_id)[0], 403)
        permissions[:] = ["audit.read"]
        self.assertEqual(http(999)[0], 404)
        self.assertEqual(http(contact_id, "?limit=51")[0], 422)
        self.assertEqual(http(contact_id, "?before_id=0")[0], 422)
        self.assertEqual(http(manual_id)[1]["data"]["state"], "unlinked")
        self.assertEqual(http(unknown_id)[1]["data"]["state"], "unrecorded")
        status, response, _ = http(contact_id, "?limit=1")
        self.assertEqual(status, 200, response)
        page = response["data"]
        self.assertEqual(page["state"], "granted")
        self.assertEqual(datetime.fromisoformat(page["decision_at"]), datetime(2026, 1, 1, 12, 3, tzinfo=timezone.utc))
        self.assertEqual(datetime.fromisoformat(page["authorized_from"]), datetime.fromisoformat(page["decision_at"]))
        prior, = page["items"]
        self.assertEqual((prior["kind"], prior["accepted"], prior["effective_at"]),
                         ("prior_withdrawal", None, "2026-01-01T12:02:00Z"))
        self.assertNotIn(phone, str(response))
        older = http(contact_id, f"?before_id={page['next_before_id']}")[1]["data"]
        self.assertEqual(older["state"], "granted")
        self.assertEqual([item["accepted"] for item in older["items"]], [True, True])
        self.assertIsNone(older["next_before_id"])
        self.assertFalse(decision(4, False)["consentimiento_datos"])
        withdrawn = http(contact_id)[1]["data"]
        self.assertEqual(withdrawn["state"], "not_granted")
        self.assertIsNone(withdrawn["authorized_from"])
        self.assertEqual(datetime.fromisoformat(withdrawn["decision_at"]), datetime(2026, 1, 1, 12, 4, tzinfo=timezone.utc))

        # Read the same evidence on a disposable tenant without the v8 projection.
        with self.engine.begin() as connection:
            WhatsAppConsentState.__table__.drop(connection.execution_options(**tenant_exec_options(tenant.schema_name)))
        legacy = http(contact_id, "?before_id=1")[1]["data"]
        self.assertEqual(legacy["state"], "not_granted")
        self.assertEqual(datetime.fromisoformat(legacy["decision_at"]), datetime.fromisoformat(withdrawn["decision_at"]))
        self.assertEqual(legacy["items"], [])
