from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente, SolicitudDerecho
from test_message_identity import PostgresCase
import test_turn_recovery


class PrivacyCaseTests(PostgresCase):
    def test_review_and_confirmed_closure_are_audited_and_isolated(self):
        first, second = self.tenant(), self.tenant()
        for workspace, kind in ((first, "eliminacion"), (second, "acceso")):
            with Session(self.engine.execution_options(**tenant_exec_options(workspace.schema_name))) as db:
                db.add(Cliente(rut="synthetic", nombre="Still present", whatsapp_id="internal-only"))
                db.add(SolicitudDerecho(id=1, whatsapp_id="internal-only", tipo_derecho=kind, notas="Internal note"))
                db.commit()
        with Session(self.engine) as db:
            for auth_id, workspace in ((81, first), (82, second)):
                db.add(TenantRuntime(auth_tenant_id=auth_id, schema_name=workspace.schema_name,
                                     tenant_slug=workspace.tenant_slug, tenant_code=workspace.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        company = 81
        permissions = ["users.read"]
        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)
        path = "/api/v1/operational/privacy-cases"

        def http(method, suffix="", payload=None):
            return test_turn_recovery.TurnRecoveryTests.http(self, method, path + suffix, payload, {"X-Tenant-ID": "82"})

        review = {"expected_state": "pendiente", "state": "en_proceso"}
        complete = {"expected_state": "en_proceso", "state": "completada", "confirmed": True}
        self.assertEqual(http("GET")[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "synthetic-actor", company, None, [], permissions, {}, {},
        )
        self.assertEqual(http("GET")[0], 403)
        permissions.append("audit.read")
        response = http("GET", "?state=pendiente")[1]
        self.assertEqual(response["meta"]["tenant_id"], "81")
        self.assertEqual(response["data"]["total"], 1)
        item = response["data"]["items"][0]
        self.assertEqual(set(item), {"id", "kind", "state", "requested_at", "due_at", "completed_at"})
        self.assertEqual(item["kind"], "eliminacion")
        self.assertEqual(http("PATCH", "/1", review)[0], 403)
        permissions.append("crm.manage")
        self.assertEqual(http("PATCH", "/2", review)[0], 404)
        self.assertEqual(http("PATCH", "/1", complete | {"expected_state": "pendiente"})[0], 422)
        self.assertEqual(http("PATCH", "/1", complete)[0], 409)
        self.assertEqual(http("PATCH", "/1", review)[0], 200)
        self.assertEqual(http("PATCH", "/1", review)[0], 200)
        self.assertEqual(http("PATCH", "/1", complete | {"confirmed": False})[0], 422)
        status, response, _ = http("PATCH", "/1", complete)
        self.assertEqual(status, 200, response)
        self.assertEqual(response["data"]["state"], "completada")
        self.assertIsNotNone(response["data"]["completed_at"])
        self.assertEqual(http("PATCH", "/1", complete)[1]["data"], response["data"])
        self.assertEqual(http("PATCH", "/1", review)[0], 409)
        self.assertEqual(http("GET", "?state=pendiente")[1]["data"]["items"], [])
        company = 82
        item = http("GET", "?state=pendiente")[1]["data"]["items"][0]
        self.assertEqual(item["kind"], "acceso")

        with Session(self.engine.execution_options(**tenant_exec_options(first.schema_name))) as db:
            self.assertEqual(db.scalar(select(Cliente.nombre)), "Still present")
            self.assertEqual(db.get(SolicitudDerecho, 1).notas, "Internal note")
            events = db.scalars(select(SystemEvent.payload).where(SystemEvent.event_type == "privacy.case.state.changed")
                                .order_by(SystemEvent.id)).all()
            self.assertEqual([{key: value for key, value in event.items() if key != "_correlation_id"} for event in events], [
                {"case_id": 1, "previous_state": "pendiente", "state": "en_proceso", "actor_id": "synthetic-actor"},
                {"case_id": 1, "previous_state": "en_proceso", "state": "completada", "actor_id": "synthetic-actor"},
            ])
