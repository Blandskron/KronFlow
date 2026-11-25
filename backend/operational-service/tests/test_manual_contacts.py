from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente
from test_message_identity import PostgresCase
import test_turn_recovery


class ManualContactTests(PostgresCase):
    def test_manual_contact_creation_and_edit_are_idempotent_and_tenant_scoped(self):
        tenant, other = self.tenant(), self.tenant()
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.add(Cliente(rut="wa:synthetic", nombre="Legacy", canal_origen="whatsapp_directo"))
            db.commit()
        with Session(self.engine) as db:
            for tenant_id, workspace in ((812, tenant), (813, other)):
                db.add(TenantRuntime(auth_tenant_id=tenant_id, schema_name=workspace.schema_name,
                                     tenant_slug=workspace.tenant_slug, tenant_code=workspace.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)
        workspace_id = 812
        permissions = ["users.read"]
        path = "/api/v1/contacts"

        def http(method, suffix="", payload=None):
            return test_turn_recovery.TurnRecoveryTests.http(self, method, path + suffix, payload, {"X-Tenant-ID": "813"})

        draft = {"request_id": str(uuid4()), "full_name": "  Contacto sintético  ", "email": "Alpha+tag@EXAMPLE.TEST"}
        self.assertEqual(http("POST", payload=draft)[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "operator", workspace_id, None, [], permissions, {}, {},
        )
        self.assertEqual(http("POST", payload=draft)[0], 403)
        self.assertEqual(http("PATCH", "/1/points", {"email": None, "phone": None, "expected_email": None, "expected_phone": None})[0], 403)
        permissions.append("crm.manage")
        for changes in ({"request_id": "invalid"}, {"full_name": " "}, {"phone": "912345678"}, {"consentimiento_datos": True}):
            with self.subTest(changes=changes):
                self.assertEqual(http("POST", payload=draft | changes)[0], 422)

        with ThreadPoolExecutor(max_workers=2) as executor:
            submissions = [executor.submit(http, "POST", "", draft) for _ in range(2)]
            results = [submission.result(timeout=15) for submission in submissions]
        self.assertEqual([result[0] for result in results], [200, 200], results)
        self.assertCountEqual([result[1]["data"]["created"] for result in results], [True, False])
        contact = results[0][1]["data"]["contact"]
        self.assertEqual(results[1][1]["data"]["contact"], contact)
        self.assertEqual((contact["full_name"], contact["email"], contact["phone"], contact["source"]),
                         ("Contacto sintético", "Alpha+tag@example.test", None, "crm_manual"))
        contact_path = f"/{contact['id']}"

        edit = {"email": None, "phone": "+56 (9) 1234-5678", "expected_email": contact["email"], "expected_phone": None}
        self.assertEqual(http("PATCH", "/1/points", edit)[0], 409)
        status, response, _ = http("PATCH", contact_path + "/points", edit)
        self.assertEqual(status, 200, response)
        saved = response["data"]
        self.assertEqual((saved["email"], saved["phone"], saved["normalized_phone"]), (None, "+56912345678", "+56912345678"))
        self.assertEqual(http("PATCH", contact_path + "/points", edit)[0], 409)
        self.assertEqual(http("PATCH", contact_path + "/points", edit | {
            "expected_email": None, "expected_phone": saved["phone"],
        })[0], 200)
        self.assertEqual(http("POST", payload=draft)[1]["data"], {"contact": saved, "created": False})
        self.assertEqual(http("GET", "?source=crm_manual")[1]["data"]["total"], 1)
        lead = http("POST", contact_path + "/lead")[1]["data"]["lead"]
        self.assertEqual((lead["contact_id"], lead["metadata"]["rut"]), (contact["id"], ""))

        workspace_id = 813
        self.assertEqual(http("PATCH", contact_path + "/points", edit)[0], 404)
        status, response, _ = http("POST", payload={"request_id": draft["request_id"], "full_name": "Solo nombre"})
        self.assertEqual(status, 200, response)
        self.assertTrue(response["data"]["created"])
        self.assertIsNone(response["data"]["contact"]["email"])

        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            record = db.get(Cliente, contact["id"])
            self.assertEqual((record.whatsapp_id, record.consentimiento_datos), (None, False))
        with Session(self.engine) as db:
            events = db.execute(select(SystemEvent.event_type, SystemEvent.payload).where(
                SystemEvent.auth_tenant_id == 812, SystemEvent.event_type.in_(("crm.contact.created", "crm.contact.points.changed")),
            ).order_by(SystemEvent.id)).all()
            self.assertEqual([(kind, {key: value for key, value in payload.items() if key != "_correlation_id"})
                              for kind, payload in events], [
                ("crm.contact.created", {"contact_id": contact["id"]}),
                ("crm.contact.points.changed", {"contact_id": contact["id"], "fields": ["email", "phone"]}),
            ])
