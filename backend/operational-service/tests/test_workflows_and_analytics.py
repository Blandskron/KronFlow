from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.core.tenant_resolver import TenantContext
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.ingest import WhatsAppMessageIn
from app.schemas.workflow import WorkflowCreateIn, WorkflowDraftUpdateIn, WorkflowGraphIn
from app.services.ai_extensions_service import record_ai_usage
from app.services.analytics_service import analytics_kpis
from app.services.consent_authorization_service import record_suppression
from app.services.ingest_service import ingest_whatsapp_message
from app.services.lead_service import ensure_contact_lead
from app.services.outbox_dispatcher import run_worker_cycle
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.workflow_service import (
    create_workflow,
    get_workflow,
    list_workflow_revisions,
    list_workflow_runs,
    list_workflow_templates,
    process_tenant_workflows,
    publish_workflow,
    simulate_workflow,
    update_workflow_draft,
    validate_workflow_graph,
)
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.ai_extensions import ExternalNotificationDelivery
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.operations import Cliente
from app.tenant_models.workflows import WorkflowRun, WorkflowStepRun
from test_message_identity import PostgresCase
from test_outbox_worker_and_unsubscribe import FakeOutboxTransport


T0 = datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=30)
T2 = T0 + timedelta(minutes=65)


class WorkflowsAndAnalyticsTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int) -> TenantContext:
        tenant = TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="pro",
            status="active",
        )
        with Session(self.engine) as db:
            apply_tenant_schema(db, schema)
            db.add(
                TenantRuntime(
                    auth_tenant_id=auth_id,
                    tenant_slug=schema,
                    schema_name=schema,
                    tenant_code=schema,
                    ingest_key_hash="unused",
                    plan="pro",
                    status="active",
                )
            )
            db.commit()
        return tenant

    def test_compiler_simulation_versioning_and_worker_execution(self):
        tenant = self._seed_tenant("tenant_wf_1", 9201)

        # 1. Static compiler validation rejects invalid trigger count, cycles, unreachable nodes, bad action/delay.
        no_trigger = validate_workflow_graph(
            "lead.created",
            {"nodes": [{"id": "a1", "type": "end", "label": "End", "config": {}}], "edges": []},
        )
        self.assertFalse(no_trigger["valid"])

        double_trigger = validate_workflow_graph(
            "lead.created",
            {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "T1", "config": {}},
                    {"id": "t2", "type": "trigger", "label": "T2", "config": {}},
                ],
                "edges": [],
            },
        )
        self.assertFalse(double_trigger["valid"])

        cyclic = validate_workflow_graph(
            "lead.created",
            {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "T", "config": {}},
                    {"id": "a1", "type": "action", "label": "A1", "config": {"action_kind": "noop"}},
                    {"id": "a2", "type": "action", "label": "A2", "config": {"action_kind": "noop"}},
                ],
                "edges": [
                    {"source": "t1", "target": "a1", "when": "always"},
                    {"source": "a1", "target": "a2", "when": "always"},
                    {"source": "a2", "target": "a1", "when": "always"},
                ],
            },
        )
        self.assertFalse(cyclic["valid"])
        self.assertTrue(any("cycle" in e for e in cyclic["errors"]))

        orphan = validate_workflow_graph(
            "lead.created",
            {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "T", "config": {}},
                    {"id": "e1", "type": "end", "label": "E", "config": {}},
                    {"id": "x1", "type": "action", "label": "Orphan", "config": {"action_kind": "noop"}},
                ],
                "edges": [{"source": "t1", "target": "e1", "when": "always"}],
            },
        )
        self.assertFalse(orphan["valid"])
        self.assertTrue(any("Unreachable" in e for e in orphan["errors"]))

        bad_delay_and_action = validate_workflow_graph(
            "lead.created",
            {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "T", "config": {}},
                    {"id": "w1", "type": "wait", "label": "W", "config": {"delay_seconds": 0}},
                    {"id": "a1", "type": "action", "label": "A", "config": {"action_kind": "delete.all"}},
                ],
                "edges": [
                    {"source": "t1", "target": "w1", "when": "always"},
                    {"source": "w1", "target": "a1", "when": "always"},
                ],
            },
        )
        self.assertFalse(bad_delay_and_action["valid"])
        self.assertGreaterEqual(len(bad_delay_and_action["errors"]), 2)

        with Session(self.engine) as db:
            templates = list_workflow_templates()
            self.assertEqual(len(templates), 3)

            # 2. Conditional workflow: simulate dry-run (0 side effects) & publish immutable r1 vs draft v3 & r2.
            branch_graph = WorkflowGraphIn(
                nodes=[
                    {"id": "t1", "type": "trigger", "label": "Trigger", "config": {}},
                    {
                        "id": "c1",
                        "type": "condition",
                        "label": "VIP?",
                        "config": {"field": "contact_id", "operator": "eq", "value": 10},
                    },
                    {
                        "id": "a_yes",
                        "type": "action",
                        "label": "Notify VIP",
                        "config": {
                            "action_kind": "notification.send",
                            "channel": "webhook_stub",
                            "recipient": "vip-desk",
                            "message": "VIP alert",
                        },
                    },
                    {"id": "a_no", "type": "action", "label": "Noop", "config": {"action_kind": "noop"}},
                    {"id": "e1", "type": "end", "label": "End", "config": {}},
                ],
                edges=[
                    {"source": "t1", "target": "c1", "when": "always"},
                    {"source": "c1", "target": "a_yes", "when": "true"},
                    {"source": "c1", "target": "a_no", "when": "false"},
                    {"source": "a_yes", "target": "e1", "when": "always"},
                    {"source": "a_no", "target": "e1", "when": "always"},
                ],
            )
            wf = create_workflow(
                db,
                tenant,
                WorkflowCreateIn(
                    name="VIP Lead Router",
                    description="Enruta leads",
                    trigger_event_type="lead.created",
                    graph=branch_graph,
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(wf["draft_version"], 1)

            sim_true = simulate_workflow(db, tenant, wf["id"], {"contact_id": 10})
            self.assertTrue(sim_true["valid"])
            self.assertEqual(sim_true["visited_nodes"], ["t1", "c1", "a_yes", "e1"])
            self.assertEqual(len(sim_true["planned_effects"]), 1)
            self.assertIn("c1->a_no(false)", sim_true["discarded_branches"])

            # Verify simulate created zero runs, outbox jobs, or proposals.
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(WorkflowRun)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(ActionOutboxJob)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(AIActionProposal)), 0)

            # Optimistic lock conflict returns 409.
            with self.assertRaises(HTTPException) as err_409:
                update_workflow_draft(
                    db,
                    tenant,
                    wf["id"],
                    WorkflowDraftUpdateIn(name="Conflict", expected_version=99),
                    now=T0,
                )
            self.assertEqual(err_409.exception.status_code, 409)

            r1 = publish_workflow(db, tenant, wf["id"], expected_version=1, actor_user_id="mgr-1", note="R1", now=T0)
            self.assertEqual(r1["revision_number"], 1)
            after_r1 = get_workflow(db, tenant, wf["id"])
            self.assertEqual(after_r1["draft_version"], 2)
            self.assertEqual(after_r1["active_revision_id"], r1["id"])

            # Edit draft without publishing: r1 stays active & immutable.
            updated = update_workflow_draft(
                db,
                tenant,
                wf["id"],
                WorkflowDraftUpdateIn(name="VIP Lead Router v2", expected_version=2),
                now=T0,
            )
            self.assertEqual(updated["active_revision_id"], r1["id"])
            r2 = publish_workflow(db, tenant, wf["id"], expected_version=3, actor_user_id="mgr-1", note="R2", now=T0)
            self.assertEqual(r2["revision_number"], 2)
            revs = list_workflow_revisions(db, tenant, wf["id"])
            self.assertEqual([(r["revision_number"], r["status"]) for r in revs], [(2, "active"), (1, "superseded")])

            # 3. Domain event lead.created triggers run once; worker cycle runs workflow AND dispatches outbox job!
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(id=10, rut="rut-10", nombre="VIP Corp", whatsapp_id="569000010"))
            db.commit()
            ensure_contact_lead(db, tenant, 10)

            SessionFactory = sessionmaker(bind=self.engine)
            transport = FakeOutboxTransport()
            worker_summary = run_worker_cycle(
                SessionFactory,
                settings=Settings(_env_file=None, worker_allow_stub_dispatch=True),
                transport=transport,
                now=T0,
            )
            self.assertEqual(worker_summary["workflow_runs_started"], 1)
            self.assertGreaterEqual(worker_summary["completed"], 1)

            # Second tick is idempotent: no duplicate run or step created.
            res_dup = process_tenant_workflows(db, tenant, now=T0)
            self.assertEqual(res_dup["runs_started"], 0)
            runs = list_workflow_runs(db, tenant, workflow_id=wf["id"])
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0]["status"], "completed")
            self.assertEqual(len(runs[0]["steps"]), 4)

            bind_tenant_session(db, tenant.schema_name)
            notif = db.scalar(select(ExternalNotificationDelivery))
            self.assertIsNotNone(notif)
            self.assertEqual(notif.status, "delivered")

            # 4. KPIs reconcile AI usage (excluding simulations) + workflow counts.
            record_ai_usage(
                db,
                tenant,
                provider="groq",
                model="llama-3.1-8b-instant",
                prompt_tokens=100,
                completion_tokens=20,
                latency_ms=80,
                estimated_cost_usd=Decimal("0.002000"),
                is_simulation=False,
                now=T0,
            )
            record_ai_usage(
                db,
                tenant,
                provider="groq",
                model="llama-3.1-8b-instant",
                prompt_tokens=500,
                completion_tokens=100,
                latency_ms=120,
                estimated_cost_usd=Decimal("0.010000"),
                is_simulation=True,
                now=T0,
            )
            kpis = analytics_kpis(db, tenant)
            self.assertEqual(kpis.ai_usage.requests, 1)
            self.assertEqual(kpis.ai_usage.total_cost_usd, "0.002000")
            self.assertEqual(kpis.workflows.active_workflows, 1)
            self.assertEqual(kpis.workflows.runs_completed, 1)

    def test_wait_timers_resume_when_due_and_cancel_atomically_on_reply_or_suppression(self):
        tenant = self._seed_tenant("tenant_wf_wait", 9202)
        wait_graph = WorkflowGraphIn(
            nodes=[
                {"id": "t1", "type": "trigger", "label": "Lead creado", "config": {}},
                {
                    "id": "w1",
                    "type": "wait",
                    "label": "Espera 1h",
                    "config": {
                        "delay_seconds": 3600,
                        "cancel_on_events": ["message.inbound.received", "contact.suppressed", "consent.withdrawn"],
                    },
                },
                {
                    "id": "a1",
                    "type": "action",
                    "label": "Notificar seguimiento",
                    "config": {
                        "action_kind": "notification.send",
                        "channel": "webhook_stub",
                        "recipient": "followup@acme.test",
                        "message": "Seguimiento programado",
                    },
                },
                {"id": "e1", "type": "end", "label": "Fin", "config": {}},
            ],
            edges=[
                {"source": "t1", "target": "w1", "when": "always"},
                {"source": "w1", "target": "a1", "when": "always"},
                {"source": "a1", "target": "e1", "when": "always"},
            ],
        )

        with Session(self.engine) as db:
            wf = create_workflow(
                db,
                tenant,
                WorkflowCreateIn(name="Followup 1h", trigger_event_type="lead.created", graph=wait_graph),
                actor_user_id="mgr-1",
                now=T0,
            )
            publish_workflow(db, tenant, wf["id"], expected_version=1, actor_user_id="mgr-1", now=T0)

            # Case A: Contact 100 never replies -> wakes at T2 (T0 + 65m > 1h) and enqueues outbox job.
            bind_tenant_session(db, tenant.schema_name)
            db.add_all(
                [
                    Cliente(id=100, rut="rut-100", nombre="Sin Respuesta", whatsapp_id="569100001"),
                    Cliente(id=200, rut="rut-200", nombre="Responde Pronto", whatsapp_id="569200002"),
                    Cliente(id=300, rut="rut-300", nombre="Se Da De Baja", whatsapp_id="569300003"),
                ]
            )
            db.commit()
            ensure_contact_lead(db, tenant, 100)
            ensure_contact_lead(db, tenant, 200)
            ensure_contact_lead(db, tenant, 300)

            start_res = process_tenant_workflows(db, tenant, now=T0)
            self.assertEqual(start_res["runs_started"], 3)
            self.assertEqual(start_res["runs_waiting"], 3)

            # Too early at T1 (30m < 60m): none resumed yet.
            early_res = process_tenant_workflows(db, tenant, now=T1)
            self.assertEqual(early_res["runs_resumed"], 0)

            # Case B: Contact 200 replies inbound via WhatsApp -> waiting run cancelled atomically in same transaction!
            ingest_whatsapp_message(
                db,
                tenant,
                WhatsAppMessageIn(
                    external_message_id="wa-reply-200",
                    phone="569200002",
                    direction="inbound",
                    body="Hola! Si me interesa",
                    sent_at=T1,
                ),
            )

            # Case C: Contact 300 gets suppressed -> waiting run cancelled atomically in same transaction!
            record_suppression(
                db,
                tenant,
                channel="whatsapp",
                destination="569300003",
                reason="baja",
                source="operational",
                client_id=300,
                recorded_at=T1,
                cancel_pending_jobs=True,
            )

            # At T2 (> 60m), only Contact 100 resumes and completes; 200 and 300 remain cancelled and execute 0 actions!
            due_res = process_tenant_workflows(db, tenant, now=T2)
            self.assertEqual(due_res["runs_resumed"], 1)
            self.assertEqual(due_res["runs_completed"], 1)

            runs = {r["contact_id"]: r for r in list_workflow_runs(db, tenant, workflow_id=wf["id"])}
            self.assertEqual(runs[100]["status"], "completed")
            self.assertEqual(runs[200]["status"], "cancelled")
            self.assertEqual(runs[200]["error_message"], "customer_replied")
            self.assertEqual(runs[300]["status"], "cancelled")
            self.assertEqual(runs[300]["error_message"], "suppressed:baja")

            # Exactly 1 notification outbox job was created (only for contact 100).
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(ActionOutboxJob)), 1)
            self.assertEqual(
                db.scalar(select(func.count()).select_from(WorkflowStepRun).where(WorkflowStepRun.node_id == "a1")),
                1,
            )

    def test_viewer_blocked_from_workflow_mutations_and_crm_manage_allowed(self):
        runtime = SimpleNamespace(
            auth_tenant_id=1, tenant_slug="test", schema_name="tenant_test", tenant_code="test", plan="free", status="active",
        )
        db = self._mock_db(runtime)
        viewer = CurrentPrincipal("1", 1, "1", ["VIEWER"], ["users.read"], {}, {})
        app.dependency_overrides.update({get_db: lambda: db, get_current_principal: lambda: viewer})
        self.addCleanup(app.dependency_overrides.clear)
        client = TestClient(app)

        tpl = list_workflow_templates()[0]
        body = {
            "name": tpl["name"],
            "description": tpl["description"],
            "trigger_event_type": tpl["trigger_event_type"],
            "graph": tpl["graph"],
        }
        self.assertEqual(client.post("/api/v1/workflows", json=body).status_code, 403)
        self.assertEqual(client.post("/api/v1/workflows/process-tick").status_code, 403)

        manager = CurrentPrincipal("2", 1, "1", ["MANAGER"], ["crm.manage"], {}, {})
        app.dependency_overrides[get_current_principal] = lambda: manager
        with patch("app.api.v1.workflows.create_workflow", return_value={
            "id": 1,
            "name": tpl["name"],
            "description": tpl["description"],
            "status": "draft",
            "trigger_event_type": tpl["trigger_event_type"],
            "draft_graph": tpl["graph"],
            "draft_version": 1,
            "active_revision_id": None,
            "active_revision_number": None,
            "created_by": "2",
            "created_at": T0.isoformat(),
            "updated_at": T0.isoformat(),
        }) as create_mock:
            res = client.post("/api/v1/workflows", json=body)
            self.assertEqual(res.status_code, 201)
            create_mock.assert_called_once()

    @staticmethod
    def _mock_db(runtime):
        from unittest.mock import MagicMock

        mock = MagicMock()
        mock.scalar.return_value = runtime
        return mock
