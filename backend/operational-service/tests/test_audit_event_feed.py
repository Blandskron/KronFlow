from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from test_message_identity import PostgresCase
import test_turn_recovery


class AuditEventFeedTests(PostgresCase):
    def test_event_catalog_projection_cursor_correlation_and_tenant_scope(self):
        current, other = self.tenant(), self.tenant()
        selected = str(uuid4())
        with Session(self.engine) as db:
            for auth_id, workspace in ((81, current), (82, other)):
                db.add(TenantRuntime(auth_tenant_id=auth_id, schema_name=workspace.schema_name,
                                     tenant_slug=workspace.tenant_slug, tenant_code=workspace.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            db.add_all([
                SystemEvent(auth_tenant_id=81, schema_name=current.schema_name, event_type="privacy.case.state.changed",
                            payload={"case_id": 5, "previous_state": "pendiente", "state": "private@example.test",
                                     "notes": "secret synthetic note", "_correlation_id": "private@example.test"}),
                SystemEvent(auth_tenant_id=82, schema_name=other.schema_name, event_type="crm.contact.created",
                            payload={"contact_id": 1, "_correlation_id": selected}),
                SystemEvent(auth_tenant_id=81, schema_name=other.schema_name, event_type="crm.contact.created",
                            payload={"contact_id": 2}),
                SystemEvent(auth_tenant_id=81, schema_name=current.schema_name, event_type="migration.failed",
                            payload={"error": "Sensitive diagnostic"}),
            ])
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        company = 81
        permissions = ["users.read", "crm.manage"]
        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)
        path = "/api/v1/operational/audit-events"

        def http(method, route, data=None, headers=None):
            return test_turn_recovery.TurnRecoveryTests.http(
                self, method, route, data, {"X-Tenant-ID": "82", **(headers or {})},
            )

        self.assertEqual(http("GET", path)[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "synthetic-actor", company, None, [], permissions, {}, {},
        )
        self.assertEqual(http("GET", path)[0], 403)
        permissions.append("audit.read")
        contacts = "/api/v1/contacts"
        draft = {"full_name": "Synthetic", "request_id": str(uuid4())}
        status, response, _ = http("POST", contacts, draft, {"X-Correlation-ID": selected})
        self.assertEqual(status, 200, response)
        created_id = response["data"]["contact"]["id"]
        self.assertEqual(response["meta"]["correlation_id"], selected)
        status, response, _ = http("GET", path + "?limit=1")
        self.assertEqual(status, 200, response)
        page = response["data"]
        self.assertIsNotNone(page["next_before_id"])
        event = page["items"][0]
        self.assertEqual((event["event_type"], event["event_version"], event["tenant_id"], event["correlation_id"]),
                         ("contact.created", "v1", "81", selected))
        self.assertEqual(event["data"], {"contact_id": created_id})
        self.assertEqual(set(event), {"event_id", "event_type", "event_version", "tenant_id", "producer",
                                      "occurred_at", "correlation_id", "trace_id", "data"})
        http("POST", contacts, draft | {"request_id": str(uuid4())}, {"X-Correlation-ID": "avoid@example.test"})
        older = http("GET", path + f"?before_id={page['next_before_id']}")[1]["data"]
        self.assertIsNone(older["next_before_id"])
        legacy, = older["items"]
        self.assertEqual(legacy["correlation_id"], legacy["event_id"])
        self.assertEqual(legacy["data"], {"case_id": 5, "previous_state": "pendiente"})
        current_page = http("GET", path + "?event_type=contact.created")[1]["data"]["items"]
        self.assertEqual(len(current_page), 2)
        self.assertEqual(current_page[0]["correlation_id"], current_page[0]["event_id"])
        correlated = http("GET", path + f"?correlation_id={selected}")[1]["data"]["items"]
        self.assertEqual(correlated, [event])
        self.assertEqual(http("GET", path + "?event_type=migration.failed")[0], 422)
        self.assertEqual(http("GET", path + "?correlation_id=invalid")[0], 422)
        company = 82
        other_items = http("GET", path + f"?correlation_id={selected}")[1]["data"]["items"]
        self.assertEqual([item["tenant_id"] for item in other_items], ["82"])
