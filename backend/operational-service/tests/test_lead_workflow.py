from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.services.lead_service import ensure_contact_lead
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente, Lead, Message
from test_message_identity import PostgresCase
import test_turn_recovery


class LeadWorkflowTests(PostgresCase):
    def test_start_qualify_and_read_history_with_separate_permissions(self):
        current, other = self.tenant(), self.tenant()
        fixture = Path(__file__).parent / "fixtures" / "manual_lead_qa.sql"
        database = self.engine.url.set(drivername="postgresql").render_as_string()
        for _ in range(2):
            self.pg("psql", "-X", "-v", "ON_ERROR_STOP=1", "-v", f"tenant_schema={current.schema_name}",
                    "--dbname", database, "--file", str(fixture))
        with Session(self.engine.execution_options(**tenant_exec_options(current.schema_name))) as db:
            self.assertEqual(db.execute(select(Cliente.id, Cliente.whatsapp_id, Cliente.consentimiento_datos)).all(),
                             [(1, None, False)])
        with Session(self.engine.execution_options(**tenant_exec_options(other.schema_name))) as db:
            db.add_all([Cliente(id=1, rut="qa:other", nombre="Synthetic B"), Cliente(id=31, rut="qa:private", nombre="Private")])
            db.commit()
        with Session(self.engine) as db:
            for tenant_id, tenant in ((812, current), (813, other)):
                db.add(TenantRuntime(auth_tenant_id=tenant_id, schema_name=tenant.schema_name, tenant_code=tenant.tenant_code,
                                     tenant_slug=tenant.tenant_slug, status="active", plan="free", ingest_key_hash="unused"))
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        workspace_id = 812
        permissions = ["users.read"]
        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)

        def http(method, path, payload=None):
            return test_turn_recovery.TurnRecoveryTests.http(self, method, path, payload, headers={"X-Tenant-ID": "813"})

        start = "/api/v1/contacts/1/lead"
        self.assertEqual(http("POST", start)[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "operator", workspace_id, None, [], permissions, {}, {},
        )
        self.assertEqual(http("POST", start)[0], 403)
        permissions.append("crm.manage")
        self.assertEqual(http("POST", "/api/v1/contacts/31/lead")[0], 404)
        status, response, _ = http("POST", start)
        self.assertEqual(status, 200, response)
        result = response["data"]
        self.assertTrue(result["created"])
        lead = result["lead"]
        self.assertEqual((lead["full_name"], lead["contact_id"], lead["phone"], lead["lifecycle_status"]),
                         ("Contacto QA sin lead", 1, "", "nuevo"))
        self.assertEqual(http("POST", start)[1]["data"], {"created": False, "lead": lead})
        lead_path = f"/api/v1/leads/{lead['id']}"
        activity = lead_path + "/activity"
        self.assertEqual(http("GET", activity)[0], 403)

        edit = {"temperature": "warm", "lifecycle_status": "contactado", "expected_updated_at": lead["updated_at"]}
        status, response, _ = http("PATCH", lead_path, edit)
        self.assertEqual(status, 200, response)
        saved = response["data"]
        self.assertEqual((saved["temperature"], saved["lifecycle_status"]), ("warm", "contactado"))
        self.assertEqual(http("PATCH", lead_path, edit)[0], 409)
        self.assertEqual(http("PATCH", lead_path, edit | {"expected_updated_at": saved["updated_at"]})[0], 200)
        self.assertEqual(http("GET", "/api/v1/leads?temperature=warm&contact_id=1")[1]["data"]["total"], 1)
        self.assertEqual(http("GET", "/api/v1/leads?temperature=cold&contact_id=1")[1]["data"]["total"], 0)

        permissions.append("audit.read")
        events = http("GET", activity)[1]["data"]
        self.assertEqual([(row["kind"], row["previous"], row["value"]) for row in events], [
            ("stage", "nuevo", "contactado"), ("temperature", "cold", "warm"), ("created", None, None),
        ])
        self.assertEqual(http("GET", activity + "?limit=1")[1]["data"], events[:1])
        workspace_id = 813
        self.assertEqual(http("GET", activity)[0], 404)
        other_start = http("POST", start)[1]["data"]
        self.assertTrue(other_start["created"])
        self.assertEqual((other_start["lead"]["id"], other_start["lead"]["full_name"]), (lead["id"], "Synthetic B"))
        self.assertEqual([event["kind"] for event in http("GET", activity)[1]["data"]], ["created"])

    def test_manual_start_and_inbound_race_reuse_one_lead(self):
        tenant = self.tenant()
        phone = "12025550138"
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.add(Cliente(rut="qa:race", nombre="Synthetic", whatsapp_id=phone))
            db.commit()

        def manual():
            with Session(self.engine) as db:
                return ensure_contact_lead(db, tenant, 1)

        with ThreadPoolExecutor(max_workers=3) as executor:
            first, second = (executor.submit(manual) for _ in range(2))
            inbound = executor.submit(self.ingest, tenant, self.payload(phone=phone))
            results = [future.result(timeout=15) for future in (first, second, inbound)]
        self.assertEqual({results[0]["lead"]["id"], results[1]["lead"]["id"], results[2]["lead_id"]}, {1})
        self.assertLessEqual(sum(result["created"] for result in results[:2]), 1)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Lead)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 1)
