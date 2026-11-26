from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.database import get_db
from app.core.rate_limit import IngestRateLimiter
from app.core.security import CurrentPrincipal, get_current_principal
from app.core.tenant_resolver import TenantContext
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.public_models.webchat import PublicWebchatWidget
from app.schemas.tool_hub import ToolCreateIn, ToolUpdateIn
from app.schemas.webchat import WebchatWidgetCreateIn
from app.schemas.workflow import WorkflowCreateIn, WorkflowGraphIn
from app.services.ai_proposal_service import get_ai_proposal
from app.services.conversation_control_service import claim_conversation, send_human_reply
from app.services.outbox_dispatcher import run_worker_cycle
from app.services.post_v1_service import (
    purge_expired_attachments,
    read_private_attachment_bytes,
    upload_private_attachment_bytes,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.tool_hub_service import create_tool, invoke_tool, list_tools, update_tool
from app.services.webchat_service import create_webchat_session, create_webchat_widget, list_webchat_messages, post_webchat_message
from app.services.workflow_service import create_workflow, list_workflow_runs, process_tenant_workflows, publish_workflow
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.operations import Cliente
from app.tenant_models.phase4_hub import WebchatSession
from test_message_identity import PostgresCase
from test_outbox_worker_and_unsubscribe import FakeOutboxTransport


T0 = datetime(2026, 11, 26, 16, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=10)


class ToolsWebchatAttachmentsTests(PostgresCase):
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

    def test_governed_tool_registry_modes_idempotency_and_quota(self):
        tenant = self._seed_tenant("tenant_p4_tools", 9301)

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(id=1, rut="rut-t1", nombre="Original", email="t1@example.test", whatsapp_id="56930001"))
            db.commit()

            tools = list_tools(db, tenant)
            self.assertGreaterEqual(len(tools), 7)

            # Custom tool creation and schema validation 422 / 409 stale version.
            custom = create_tool(
                db,
                tenant,
                ToolCreateIn(
                    tool_key="crm.custom.echo",
                    name="Eco gobernado",
                    effect_mode="read_only",
                    input_schema={
                        "type": "object",
                        "required": ["code"],
                        "properties": {"code": {"type": "string", "maxLength": 12}},
                    },
                    max_calls_per_hour=2,
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(custom["schema_version"], 1)

            with self.assertRaises(HTTPException) as bad_args:
                invoke_tool(
                    db,
                    tenant,
                    tool_key="crm.custom.echo",
                    arguments={"code": "x" * 30},
                    idempotency_key="k-bad",
                    actor_user_id="mgr-1",
                    now=T0,
                )
            self.assertEqual(bad_args.exception.status_code, 422)

            updated_tool = update_tool(
                db,
                tenant,
                custom["id"],
                ToolUpdateIn(
                    input_schema={
                        "type": "object",
                        "required": ["code"],
                        "properties": {"code": {"type": "string", "maxLength": 20}},
                    }
                ),
                now=T0,
            )
            self.assertEqual(updated_tool["schema_version"], 2)

            with self.assertRaises(HTTPException) as stale_ver:
                invoke_tool(
                    db,
                    tenant,
                    tool_key="crm.custom.echo",
                    arguments={"code": "ok"},
                    idempotency_key="k-stale",
                    actor_user_id="mgr-1",
                    expected_schema_version=1,
                    now=T0,
                )
            self.assertEqual(stale_ver.exception.status_code, 409)

            # 1. read_only lookup executes directly + quota limit enforced on 3rd call.
            lookup = invoke_tool(
                db,
                tenant,
                tool_key="crm.contact.lookup",
                arguments={"client_id": 1},
                idempotency_key="lookup-1",
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(lookup["status"], "completed")
            self.assertTrue(lookup["result_json"]["found"])

            # Idempotency replay returns same invocation; different args with same key returns 409.
            call_1 = invoke_tool(
                db,
                tenant,
                tool_key="crm.custom.echo",
                arguments={"code": "uno"},
                idempotency_key="echo-1",
                actor_user_id="mgr-1",
                now=T0,
            )
            call_1_dup = invoke_tool(
                db,
                tenant,
                tool_key="crm.custom.echo",
                arguments={"code": "uno"},
                idempotency_key="echo-1",
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertFalse(call_1["duplicate"])
            self.assertTrue(call_1_dup["duplicate"])
            self.assertEqual(call_1["id"], call_1_dup["id"])

            with self.assertRaises(HTTPException) as conflict_args:
                invoke_tool(
                    db,
                    tenant,
                    tool_key="crm.custom.echo",
                    arguments={"code": "dos"},
                    idempotency_key="echo-1",
                    actor_user_id="mgr-1",
                    now=T0,
                )
            self.assertEqual(conflict_args.exception.status_code, 409)

            invoke_tool(
                db,
                tenant,
                tool_key="crm.custom.echo",
                arguments={"code": "dos"},
                idempotency_key="echo-2",
                actor_user_id="mgr-1",
                now=T0,
            )
            with self.assertRaises(HTTPException) as quota_err:
                invoke_tool(
                    db,
                    tenant,
                    tool_key="crm.custom.echo",
                    arguments={"code": "tres"},
                    idempotency_key="echo-3",
                    actor_user_id="mgr-1",
                    now=T0,
                )
            self.assertEqual(quota_err.exception.status_code, 429)

            # 2. proposal_required creates pending AIActionProposal without mutating contact directly.
            prop_inv = invoke_tool(
                db,
                tenant,
                tool_key="crm.contact.rename",
                arguments={"resource_id": 1, "name": "Nombre Propuesto"},
                idempotency_key="rename-1",
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(prop_inv["status"], "proposed")
            self.assertIsNotNone(prop_inv["proposal_id"])
            self.assertEqual(get_ai_proposal(db, tenant, prop_inv["proposal_id"])["status"], "pending")
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.get(Cliente, 1).nombre, "Original")

            # 3. outbox_async queues durable ActionOutboxJob.
            notif_inv = invoke_tool(
                db,
                tenant,
                tool_key="notification.send",
                arguments={"channel": "webhook_stub", "recipient": "ops@acme.test", "event_type": "ping"},
                idempotency_key="notif-1",
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(notif_inv["status"], "queued")
            self.assertIsNotNone(notif_inv["outbox_job_id"])
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(ActionOutboxJob)), 1)

    def test_webchat_signed_sessions_origin_guard_hitl_and_workflow_cancel(self):
        tenant = self._seed_tenant("tenant_p4_wc", 9302)
        limiter = IngestRateLimiter("", window_seconds=60)

        with Session(self.engine) as db:
            # Wildcard origin rejected 422.
            with self.assertRaises(HTTPException) as wild_err:
                create_webchat_widget(
                    db,
                    tenant,
                    WebchatWidgetCreateIn(name="Bad", allowed_origins=["https://*.example.com"]),
                    actor_user_id="mgr-1",
                    now=T0,
                )
            self.assertEqual(wild_err.exception.status_code, 422)

            widget = create_webchat_widget(
                db,
                tenant,
                WebchatWidgetCreateIn(
                    name="Sitio Principal",
                    allowed_origins=["https://shop.acme.test:8443"],
                    welcome_message="Hola, bienvenido a ACME",
                ),
                actor_user_id="mgr-1",
                now=T0,
            )

            # Unlisted origin blocked with 403.
            with self.assertRaises(HTTPException) as origin_err:
                create_webchat_session(
                    db,
                    widget_key=widget["widget_key"],
                    origin="https://evil.example",
                    limiter=limiter,
                    now=T0,
                )
            self.assertEqual(origin_err.exception.status_code, 403)

            # Publish waiting workflow on lead.created before visitor session creation so lead.created triggers it.
            wait_wf = create_workflow(
                db,
                tenant,
                WorkflowCreateIn(
                    name="Wait WF",
                    trigger_event_type="lead.created",
                    graph=WorkflowGraphIn(
                        nodes=[
                            {"id": "t1", "type": "trigger", "label": "T", "config": {}},
                            {"id": "w1", "type": "wait", "label": "W", "config": {"delay_seconds": 3600}},
                            {"id": "e1", "type": "end", "label": "E", "config": {}},
                        ],
                        edges=[
                            {"source": "t1", "target": "w1", "when": "always"},
                            {"source": "w1", "target": "e1", "when": "always"},
                        ],
                    ),
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            publish_workflow(db, tenant, wait_wf["id"], expected_version=1, actor_user_id="mgr-1", now=T0)

            session_res = create_webchat_session(
                db,
                widget_key=widget["widget_key"],
                origin="https://shop.acme.test:8443",
                visitor_name="Lucia",
                visitor_email="lucia@acme.test",
                limiter=limiter,
                now=T0,
            )
            raw_token = session_res["session_token"]
            conv_id = session_res["conversation_id"]
            cursor = session_res["cursor"]

            # Verify raw token is NOT persisted (only SHA-256 hash).
            bind_tenant_session(db, tenant.schema_name)
            wc_row = db.scalar(select(WebchatSession))
            self.assertIsNotNone(wc_row)
            self.assertNotEqual(wc_row.token_hash, raw_token)
            self.assertEqual(wc_row.token_hash, hashlib.sha256(raw_token.encode()).hexdigest())

            process_tenant_workflows(db, tenant, now=T0)
            self.assertEqual(list_workflow_runs(db, tenant, workflow_id=wait_wf["id"])[0]["status"], "waiting")

            # Post inbound visitor message -> AI replies + cancels waiting workflow + idempotency.
            post1 = post_webchat_message(
                db,
                widget_key=widget["widget_key"],
                session_token=raw_token,
                origin="https://shop.acme.test:8443",
                body="Necesito cotización",
                idempotency_key="msg-1",
                reply_provider=lambda *_args: "Claro, con gusto te ayudamos con tu cotización.",
                limiter=limiter,
                now=T1,
            )
            self.assertFalse(post1["duplicate"])
            self.assertFalse(post1["ai_paused"])
            self.assertIn("cotización", post1["reply_message"]["body"])
            self.assertEqual(list_workflow_runs(db, tenant, workflow_id=wait_wf["id"])[0]["status"], "cancelled")

            post1_dup = post_webchat_message(
                db,
                widget_key=widget["widget_key"],
                session_token=raw_token,
                origin="https://shop.acme.test:8443",
                body="Necesito cotización",
                idempotency_key="msg-1",
                limiter=limiter,
                now=T1,
            )
            self.assertTrue(post1_dup["duplicate"])

            # Invalid/expired token returns 401.
            with self.assertRaises(HTTPException) as bad_tok:
                post_webchat_message(
                    db,
                    widget_key=widget["widget_key"],
                    session_token="wct_wrong",
                    origin="https://shop.acme.test:8443",
                    body="Hola",
                    idempotency_key="msg-bad",
                    limiter=limiter,
                    now=T1,
                )
            self.assertEqual(bad_tok.exception.status_code, 401)

            # Live HITL continuity: operator claims -> sends human reply -> worker delivers -> visitor polls cursor & AI pauses.
            claim_conversation(db, tenant, conv_id, actor_user_id="op-7", expected_version=1, reason="Atención humana", now=T1)
            send_human_reply(db, tenant, conv_id, actor_user_id="op-7", body="Hola Lucia, te atiende Marco.", idempotency_key="hr-1", now=T1)

            SessionFactory = sessionmaker(bind=self.engine)
            summary = run_worker_cycle(
                SessionFactory,
                settings=Settings(_env_file=None),
                transport=FakeOutboxTransport(),
                now=T1,
            )
            self.assertGreaterEqual(summary["completed"], 1)

            # Next visitor message while human owns thread returns ai_paused=True without AI reply.
            post2 = post_webchat_message(
                db,
                widget_key=widget["widget_key"],
                session_token=raw_token,
                origin="https://shop.acme.test:8443",
                body="Gracias Marco",
                idempotency_key="msg-2",
                limiter=limiter,
                now=T1,
            )
            self.assertTrue(post2["ai_paused"])
            self.assertIsNone(post2["reply_message"])
            self.assertEqual(post2["control_mode"], "human_active")

            polled = list_webchat_messages(
                db,
                widget_key=widget["widget_key"],
                session_token=raw_token,
                origin="https://shop.acme.test:8443",
                after_id=cursor,
                now=T1,
            )
            bodies = [item["body"] for item in polled["items"]]
            self.assertIn("Hola Lucia, te atiende Marco.", bodies)
            self.assertEqual(polled["control_mode"], "human_active")

    def test_private_attachment_real_bytes_download_and_purge(self):
        tenant = self._seed_tenant("tenant_p4_att", 9303)
        with tempfile.TemporaryDirectory() as tmp_dir, Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(id=1, rut="rut-a1", nombre="Adjuntos SA"))
            db.commit()

            payload_bytes = b"Factura #001\nTotal: 19900 CLP\n"
            att = upload_private_attachment_bytes(
                db,
                tenant,
                resource_type="contact",
                resource_id=1,
                filename="factura.txt",
                content_type="text/plain",
                data=payload_bytes,
                uploaded_by="op-1",
                retention_days=7,
                storage_dir=tmp_dir,
                now=T0,
            )
            self.assertEqual(att["size_bytes"], len(payload_bytes))
            self.assertEqual(att["sha256_hex"], hashlib.sha256(payload_bytes).hexdigest())

            meta, read_bytes = read_private_attachment_bytes(
                db,
                tenant,
                att["id"],
                resource_type="contact",
                resource_id=1,
                storage_dir=tmp_dir,
                now=T0,
            )
            self.assertEqual(read_bytes, payload_bytes)
            self.assertEqual(meta["filename"], "factura.txt")

            stored_file = Path(tmp_dir) / att["storage_key"]
            self.assertTrue(stored_file.is_file())

            # Wrong resource rejected 404.
            with self.assertRaises(HTTPException) as wrong_res:
                read_private_attachment_bytes(
                    db,
                    tenant,
                    att["id"],
                    resource_type="conversation",
                    resource_id=1,
                    storage_dir=tmp_dir,
                    now=T0,
                )
            self.assertEqual(wrong_res.exception.status_code, 404)

            # Expiry purge removes both DB row and physical file.
            after_exp = T0 + timedelta(days=8)
            self.assertEqual(purge_expired_attachments(db, tenant, storage_dir=tmp_dir, now=after_exp), 1)
            self.assertFalse(stored_file.exists())

    def test_viewer_blocked_from_tools_widgets_and_attachment_upload(self):
        runtime = SimpleNamespace(
            auth_tenant_id=1, tenant_slug="test", schema_name="tenant_test", tenant_code="test", plan="free", status="active",
        )
        db = MagicMock()
        db.scalar.return_value = runtime
        viewer = CurrentPrincipal("1", 1, "1", ["VIEWER"], ["users.read"], {}, {})
        app.dependency_overrides.update({get_db: lambda: db, get_current_principal: lambda: viewer})
        self.addCleanup(app.dependency_overrides.clear)
        client = TestClient(app)

        self.assertEqual(
            client.post("/api/v1/tools", json={"tool_key": "crm.x.y", "name": "X"}).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/v1/tool-invocations",
                json={"tool_key": "crm.contact.lookup", "arguments": {"client_id": 1}, "idempotency_key": "k1"},
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/v1/webchat/widgets",
                json={"name": "W", "allowed_origins": ["https://site.example"]},
            ).status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/v1/attachments/upload",
                data={"resource_type": "contact", "resource_id": "1"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            ).status_code,
            403,
        )

        # Authorized manager passes permission guard and invokes multipart upload route cleanly.
        manager = CurrentPrincipal("2", 1, "1", ["MANAGER"], ["crm.manage"], {}, {})
        app.dependency_overrides[get_current_principal] = lambda: manager
        with patch(
            "app.api.v1.post_v1.upload_private_attachment_bytes",
            return_value={
                "id": 99,
                "resource_type": "contact",
                "resource_id": 1,
                "filename": "hello.txt",
                "content_type": "text/plain",
                "size_bytes": 5,
                "sha256_hex": "b" * 64,
                "storage_key": "k",
                "uploaded_by": "2",
                "expires_at": T1.isoformat(),
                "created_at": T0.isoformat(),
            },
        ) as upload_mock:
            res = client.post(
                "/api/v1/attachments/upload",
                data={"resource_type": "contact", "resource_id": "1"},
                files={"file": ("hello.txt", b"hello", "text/plain")},
            )
            self.assertEqual(res.status_code, 201)
            upload_mock.assert_called_once()
