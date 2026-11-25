from dataclasses import replace
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.ingest import ConsentIn, HandoffIn
from app.schemas.whatsapp_turn import TurnClaimIn, TurnPrepareIn
from app.services.conversation_service import list_conversations
from app.services.ingest_service import create_handoff, save_consent
from app.services.handoff_history import list_handoff_history
from app.services.lead_service import ensure_contact_lead
from app.services.tenant_data import tenant_exec_options
from app.services.tenant_provisioning_service import create_system_event
from app.services.whatsapp_turn_service import claim_turn, prepare_turn
from app.tenant_models.operations import ConversacionResumen, Lead
from app.tenant_models.whatsapp_turn import WhatsAppTurn
from test_message_identity import PostgresCase
import test_turn_recovery


class HandoffHistoryTests(PostgresCase):
    def call(self, service, tenant, *args):
        with Session(self.engine) as db:
            return service(db, tenant, *args)

    def test_history_paginates_real_events_and_resolves_only_local_targets(self):
        tenant = replace(self.tenant(), auth_tenant_id=812)
        other = replace(self.tenant(), auth_tenant_id=813)
        contact_a, contact_b = "12025550138", "12025550139"
        missing = self.call(create_handoff, tenant, HandoffIn(phone="12025550140"))
        legacy = self.call(create_handoff, tenant, HandoffIn(phone=contact_b, reason="sensitive synthetic text"))
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.delete(db.get(Lead, missing["lead_id"]))
            db.commit()
        self.call(create_handoff, other, HandoffIn(phone=contact_b))
        self.call(save_consent, tenant, ConsentIn(phone=contact_a, accepted=True))
        claim = self.call(claim_turn, tenant, TurnClaimIn(**self.payload(phone=contact_a, full_name="Synthetic A").model_dump()))
        prepared = TurnPrepareIn(claim_token=claim["claim_token"], reply_body="private synthetic body", requires_human=True)
        for _ in range(2):
            self.call(prepare_turn, tenant, claim["turn_id"], prepared)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            conversation_id, lead_id = db.execute(select(WhatsAppTurn.conversation_id, WhatsAppTurn.lead_id)).one()
            db.execute(update(Lead).where(Lead.id == lead_id).values(estado_seguimiento="pendiente"))
            db.commit()
        self.assertEqual(self.call(list_conversations, tenant, 25, 0, None, None, True), ([], 0))

        with Session(self.engine) as db:
            for workspace in (tenant, other):
                db.add(TenantRuntime(auth_tenant_id=workspace.auth_tenant_id, schema_name=workspace.schema_name,
                                     tenant_slug=workspace.tenant_slug, tenant_code=workspace.tenant_code,
                                     ingest_key_hash="unused", status="active", plan="free"))
            create_system_event(db, "whatsapp.turn.handoff", 812, other.schema_name, {"turn_id": 1})
            create_system_event(db, "ingest.handoff.created", 813, tenant.schema_name, {"lead_id": 1})
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        workspace_id = 812
        permissions = []
        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)
        path = "/api/v1/conversations/handoff-history"

        def http(query=""):
            return test_turn_recovery.TurnRecoveryTests.http(self, "GET", path + query, headers={"X-Tenant-ID": "813"})

        self.assertEqual(http()[0], 401)
        app.dependency_overrides[get_current_principal] = lambda: CurrentPrincipal(
            "operator", workspace_id, None, [], permissions, {}, {},
        )
        self.assertEqual(http()[0], 403)
        permissions.append("users.read")
        self.assertEqual(http("?before_id=0")[0], 422)
        self.assertEqual(http("?limit=51")[0], 422)
        status, first, _ = http("?limit=1")
        self.assertEqual(status, 200, first)
        self.assertEqual(first["meta"]["tenant_id"], "812")
        newest = first["data"]["items"][0]
        self.assertEqual(set(newest), {"id", "kind", "occurred_at", "conversation_id", "lead_id", "contact_name"})
        self.assertEqual((newest["kind"], newest["conversation_id"], newest["contact_name"]),
                         ("whatsapp_turn", conversation_id, "Synthetic A"))
        self.assertEqual(first["data"]["next_before_id"], newest["id"])
        self.call(create_handoff, tenant, HandoffIn(phone=contact_b))
        status, older, _ = http(f"?before_id={newest['id']}&limit=2")
        self.assertEqual(status, 200, older)
        self.assertIsNone(older["data"]["next_before_id"])
        inbound, unavailable = older["data"]["items"]
        self.assertEqual((inbound["kind"], inbound["conversation_id"], inbound["lead_id"]),
                         ("inbound_handoff", None, legacy["lead_id"]))
        self.assertIsNone(unavailable["lead_id"])
        self.assertIsNone(unavailable["contact_name"])
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.execute(delete(ConversacionResumen).where(ConversacionResumen.whatsapp_id == contact_a))
            db.commit()
        history = http()[1]["data"]["items"]
        without_thread = next(event for event in history if event["id"] == newest["id"])
        self.assertEqual((without_thread["conversation_id"], without_thread["lead_id"]), (None, lead_id))
        workspace_id = 813
        other_result = http()[1]["data"]["items"]
        self.assertEqual(len(other_result), 1)
        self.assertEqual(other_result[0]["kind"], "inbound_handoff")

    def test_manual_fixture_is_repeatable_and_keeps_current_queue_empty(self):
        tenant = self.tenant()
        database = self.engine.url.set(drivername="postgresql").render_as_string()
        fixtures = Path(__file__).parent / "fixtures"
        args = ("-X", "-v", "ON_ERROR_STOP=1", "-v", "operational_schema=public",
                "-v", f"tenant_schema={tenant.schema_name}", "--dbname", database)
        with Session(self.engine) as db:
            db.add(TenantRuntime(auth_tenant_id=tenant.auth_tenant_id, schema_name=tenant.schema_name,
                                 tenant_slug=tenant.tenant_slug, tenant_code=tenant.tenant_code,
                                 ingest_key_hash="unused", status="active", plan="free"))
            db.commit()
        self.pg("psql", *args, "--file", str(fixtures / "manual_lead_qa.sql"))
        self.call(ensure_contact_lead, tenant, 1)
        for _ in range(2):
            self.pg("psql", *args, "--file", str(fixtures / "manual_handoff_qa.sql"))
        history = self.call(list_handoff_history, tenant, 25, None)
        self.assertEqual(len(history.items), 2)
        self.assertEqual({event.lead_id for event in history.items}, {None, 1})
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalars(select(Lead.estado_seguimiento)).all(), ["pendiente"])
            self.assertEqual(db.scalars(select(WhatsAppTurn.id)).all(), [])
