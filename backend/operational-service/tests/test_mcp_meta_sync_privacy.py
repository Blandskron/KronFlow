from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from pathlib import Path
import tempfile

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import IngestRateLimiter
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.integrations import (
    ChannelWebhookRouteCreateIn,
    ExternalMappingResolveIn,
    ExternalMappingUpsertIn,
    SyncCursorUpsertIn,
)
from app.schemas.webchat import WebchatWidgetCreateIn
from app.schemas.workflow import WorkflowCreateIn, WorkflowGraphIn
from app.services.capture_service import issue_scoped_credential, revoke_scoped_credential
from app.services.integrations_service import (
    create_webhook_route,
    deactivate_webhook_route,
    ingest_meta_webhook,
    list_external_mappings,
    list_sync_cursors,
    resolve_external_mapping_conflict,
    upsert_external_mapping,
    upsert_sync_cursor,
    verify_meta_webhook_challenge,
)
from app.services.post_v1_service import upload_private_attachment_bytes
from app.services.privacy_case_service import execute_privacy_erasure, export_privacy_case_data
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.webchat_service import create_webchat_session, create_webchat_widget
from app.services.workflow_service import create_workflow, list_workflow_runs, process_tenant_workflows, publish_workflow
from app.core.tenant_resolver import TenantContext
from app.tenant_models.ai_extensions import ConversationMemoryItem
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.consent_ledger import ContactSuppression
from app.tenant_models.operations import Cliente, Conversation, Lead, Message, SolicitudDerecho
from app.tenant_models.phase4_hub import ToolInvocation, WebchatSession
from app.tenant_models.post_v1 import PrivateAttachment
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=5)


def _meta_signature(secret: str, raw_body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


class McpMetaSyncPrivacyTests(PostgresCase):
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

    def _override_db(self):
        def _db_gen():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = _db_gen
        self.addCleanup(app.dependency_overrides.clear)

    def test_mcp_scoped_key_permissions_call_and_revocation(self):
        tenant = self._seed_tenant("tenant_p5_mcp", 9401)
        self._override_db()

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(id=1, rut="rut-m1", nombre="Cliente Original", email="m1@example.test", whatsapp_id="56940001"))
            db.commit()
            read_cred = issue_scoped_credential(db, tenant, name="mcp-reader", scopes=["mcp:read"], created_by="mgr-1")
            invoke_cred = issue_scoped_credential(
                db,
                tenant,
                name="mcp-runner",
                scopes=["mcp:read", "mcp:invoke"],
                created_by="mgr-1",
            )

        client = TestClient(app)
        init_res = client.post(
            "/api/v1/mcp",
            headers={"X-Flowkron-Key": read_cred["api_key"]},
            json={"jsonrpc": "2.0", "id": "1", "method": "initialize", "params": {}},
        )
        self.assertEqual(init_res.status_code, 200)
        self.assertEqual(init_res.json()["result"]["serverInfo"]["name"], "kronflow-operational-mcp")

        list_res = client.post(
            "/api/v1/mcp",
            headers={"X-Flowkron-Key": read_cred["api_key"]},
            json={"jsonrpc": "2.0", "id": "2", "method": "tools/list", "params": {}},
        )
        self.assertEqual(list_res.status_code, 200)
        tool_names = [t["name"] for t in list_res.json()["result"]["tools"]]
        self.assertIn("crm.contact.rename", tool_names)

        # Read-only credential cannot invoke tools/call.
        forbidden = client.post(
            "/api/v1/mcp",
            headers={"X-Flowkron-Key": read_cred["api_key"]},
            json={
                "jsonrpc": "2.0",
                "id": "3",
                "method": "tools/call",
                "params": {"name": "crm.contact.rename", "arguments": {"resource_id": 1, "name": "Nuevo"}},
            },
        )
        self.assertEqual(forbidden.status_code, 403)

        # Invoke credential runs proposal_required tool with Idempotency-Key.
        call_1 = client.post(
            "/api/v1/mcp",
            headers={"X-Flowkron-Key": invoke_cred["api_key"], "Idempotency-Key": "mcp-idem-1"},
            json={
                "jsonrpc": "2.0",
                "id": "4",
                "method": "tools/call",
                "params": {"name": "crm.contact.rename", "arguments": {"resource_id": 1, "name": "Editado"}},
            },
        )
        self.assertEqual(call_1.status_code, 200)
        meta_1 = call_1.json()["result"]["_meta"]
        self.assertEqual(meta_1["status"], "proposed")
        self.assertIsNotNone(meta_1["proposal_id"])

        call_dup = client.post(
            "/api/v1/mcp",
            headers={"X-Flowkron-Key": invoke_cred["api_key"], "Idempotency-Key": "mcp-idem-1"},
            json={
                "jsonrpc": "2.0",
                "id": "5",
                "method": "tools/call",
                "params": {"name": "crm.contact.rename", "arguments": {"resource_id": 1, "name": "Editado"}},
            },
        )
        self.assertEqual(call_dup.status_code, 200)
        dup_text = json.loads(call_dup.json()["result"]["content"][0]["text"])
        self.assertTrue(dup_text["duplicate"])

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(AIActionProposal)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(ToolInvocation)), 1)
            revoke_scoped_credential(db, tenant, invoke_cred["id"])

        revoked = client.post(
            "/api/v1/mcp",
            headers={"X-Flowkron-Key": invoke_cred["api_key"]},
            json={"jsonrpc": "2.0", "id": "6", "method": "tools/list", "params": {}},
        )
        self.assertEqual(revoked.status_code, 401)

    def test_meta_omnichannel_webhooks_isolation_receipts_and_cancellation(self):
        tenant_a = self._seed_tenant("tenant_p5_ig", 9402)
        tenant_b = self._seed_tenant("tenant_p5_msg", 9403)
        self._override_db()

        with Session(self.engine) as db:
            ig_route = create_webhook_route(
                db,
                tenant_a,
                ChannelWebhookRouteCreateIn(
                    channel="instagram",
                    external_account_id="ig-acct-1",
                    verify_token="ig_verify_tok_123",
                    app_secret="ig_secret_abc123",
                ),
                actor_user_id="mgr-a",
                now=T0,
            )
            wa_route = create_webhook_route(
                db,
                tenant_a,
                ChannelWebhookRouteCreateIn(
                    channel="whatsapp",
                    external_account_id="wa-phone-1",
                    verify_token="wa_verify_tok_123",
                    app_secret="wa_secret_abc123",
                ),
                actor_user_id="mgr-a",
                now=T0,
            )
            create_webhook_route(
                db,
                tenant_b,
                ChannelWebhookRouteCreateIn(
                    channel="messenger",
                    external_account_id="fb-page-2",
                    verify_token="fb_verify_tok_123",
                    app_secret="fb_secret_abc123",
                ),
                actor_user_id="mgr-b",
                now=T0,
            )

            # Seed tenant_a contact + waiting workflow to verify inbound IG cancels waiting run.
            bind_tenant_session(db, tenant_a.schema_name)
            c_a = Cliente(rut="rut-ig-1", nombre="IG Visitor", whatsapp_id="instagram:ig-acct-1:sender-99")
            db.add(c_a)
            db.flush()
            l_a = Lead(cliente_id=c_a.id, estado="nuevo", clasificacion="tibio")
            db.add(l_a)
            db.commit()

            wf = create_workflow(
                db,
                tenant_a,
                WorkflowCreateIn(
                    name="Cancel on Meta reply",
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
                actor_user_id="mgr-a",
                now=T0,
            )
            publish_workflow(db, tenant_a, wf["id"], expected_version=1, actor_user_id="mgr-a", now=T0)

            from app.services.domain_event_service import publish_domain_event_in_tx

            bind_tenant_session(db, tenant_a.schema_name)
            publish_domain_event_in_tx(
                db,
                tenant_a,
                event_type="lead.created",
                aggregate_type="lead",
                aggregate_id=l_a.id,
                payload={"lead_id": l_a.id, "contact_id": c_a.id},
                occurred_at=T0,
            )
            db.commit()
            process_tenant_workflows(db, tenant_a, now=T0)
            self.assertEqual(list_workflow_runs(db, tenant_a, workflow_id=wf["id"])[0]["status"], "waiting")

        client = TestClient(app)
        # Challenge checks via HTTP.
        ok_ch = client.get(
            "/api/v1/public/webhooks/meta/instagram",
            params={"hub.mode": "subscribe", "hub.verify_token": "ig_verify_tok_123", "hub.challenge": "998877"},
        )
        self.assertEqual(ok_ch.status_code, 200)
        self.assertEqual(ok_ch.text, "998877")

        bad_ch = client.get(
            "/api/v1/public/webhooks/meta/instagram",
            params={"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "998877"},
        )
        self.assertEqual(bad_ch.status_code, 403)

        # Signed Instagram inbound event + bad signature check.
        ig_payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "ig-acct-1",
                    "messaging": [
                        {
                            "sender": {"id": "sender-99"},
                            "message": {"mid": "ig-mid-1", "text": "Hola por Instagram"},
                        }
                    ],
                }
            ],
        }
        ig_raw = json.dumps(ig_payload).encode("utf-8")
        bad_sig = client.post(
            "/api/v1/public/webhooks/meta/instagram",
            content=ig_raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
        )
        self.assertEqual(bad_sig.status_code, 401)

        good_ig = client.post(
            "/api/v1/public/webhooks/meta/instagram",
            content=ig_raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _meta_signature("ig_secret_abc123", ig_raw)},
        )
        self.assertEqual(good_ig.status_code, 200)
        self.assertEqual(good_ig.json()["data"]["ingested"], 1)

        # Duplicate mid is deduplicated cleanly.
        dup_ig = client.post(
            "/api/v1/public/webhooks/meta/instagram",
            content=ig_raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _meta_signature("ig_secret_abc123", ig_raw)},
        )
        self.assertEqual(dup_ig.status_code, 200)
        self.assertEqual(dup_ig.json()["data"]["ingested"], 0)
        self.assertEqual(dup_ig.json()["data"]["duplicates"], 1)

        # Messenger webhook with same remote sender "sender-99" goes only to tenant_b.
        fb_payload = {
            "object": "page",
            "entry": [
                {
                    "id": "fb-page-2",
                    "messaging": [
                        {"sender": {"id": "sender-99"}, "message": {"mid": "fb-mid-1", "text": "Hola Messenger"}}
                    ],
                }
            ],
        }
        fb_raw = json.dumps(fb_payload).encode("utf-8")
        good_fb = client.post(
            "/api/v1/public/webhooks/meta/messenger",
            content=fb_raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _meta_signature("fb_secret_abc123", fb_raw)},
        )
        self.assertEqual(good_fb.status_code, 200)

        with Session(self.engine) as db:
            # Verify workflow cancelled and tenant isolation held.
            self.assertEqual(list_workflow_runs(db, tenant_a, workflow_id=wf["id"])[0]["status"], "cancelled")
            bind_tenant_session(db, tenant_a.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 1)
            bind_tenant_session(db, tenant_b.schema_name)
            convs_b = list(db.scalars(select(Conversation)).all())
            self.assertEqual(len(convs_b), 1)
            self.assertEqual(convs_b[0].session_id, "messenger:fb-page-2:sender-99")

            # Monotonic status progression on WhatsApp receipt updates.
            bind_tenant_session(db, tenant_a.schema_name)
            msg = Message(
                whatsapp_id="56940009",
                rol="agente",
                direction="outbound",
                connection_id="meta_whatsapp:wa-phone-1",
                channel="whatsapp",
                mensaje="Seguimiento",
                external_message_id="wamid.out.1",
                provider_message_id="wamid.out.1",
                delivery_status="sent",
            )
            db.add(msg)
            db.commit()

            for status_name in ("read", "delivered"):
                wa_payload = {
                    "object": "whatsapp_business_account",
                    "entry": [
                        {
                            "changes": [
                                {
                                    "value": {
                                        "metadata": {"phone_number_id": "wa-phone-1"},
                                        "statuses": [{"id": "wamid.out.1", "status": status_name}],
                                    }
                                }
                            ]
                        }
                    ],
                }
                wa_raw = json.dumps(wa_payload).encode("utf-8")
                res = ingest_meta_webhook(
                    db,
                    channel="whatsapp",
                    raw_body=wa_raw,
                    signature_header=_meta_signature("wa_secret_abc123", wa_raw),
                    payload=wa_payload,
                    now=T1,
                )
                self.assertEqual(res["receipts_updated"], 1 if status_name == "read" else 0)

            bind_tenant_session(db, tenant_a.schema_name)
            db.refresh(msg)
            self.assertEqual(msg.delivery_status, "read")

            deactivated = deactivate_webhook_route(db, tenant_a, ig_route["id"], now=T1)
            self.assertFalse(deactivated["is_active"])
            self.assertTrue(wa_route["is_active"])

    def test_sync_mapping_conflict_resolution_and_cursors(self):
        tenant = self._seed_tenant("tenant_p5_sync", 9404)
        with Session(self.engine) as db:
            m1 = upsert_external_mapping(
                db,
                tenant,
                ExternalMappingUpsertIn(
                    connection_ref="hubspot-main",
                    resource_type="contact",
                    remote_id="hs-101",
                    local_type="contact",
                    local_id="12",
                    remote_version="v1",
                    payload={"email": "a@acme.test"},
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(m1["sync_state"], "synced")
            self.assertEqual(m1["local_version"], 1)

            conflict = upsert_external_mapping(
                db,
                tenant,
                ExternalMappingUpsertIn(
                    connection_ref="hubspot-main",
                    resource_type="contact",
                    remote_id="hs-101",
                    local_type="contact",
                    local_id="13",
                    remote_version="v2",
                    expected_local_version=99,
                    payload={"email": "conflict@acme.test"},
                ),
                now=T1,
            )
            self.assertEqual(conflict["sync_state"], "conflict")
            self.assertEqual(conflict["conflict_payload"]["incoming_remote_version"], "v2")
            self.assertEqual(len(list_external_mappings(db, tenant, sync_state="conflict")), 1)

            resolved = resolve_external_mapping_conflict(
                db,
                tenant,
                conflict["id"],
                ExternalMappingResolveIn(resolution="synced", remote_version="v2"),
                actor_user_id="mgr-1",
                now=T1,
            )
            self.assertEqual(resolved["sync_state"], "synced")
            self.assertEqual(resolved["local_version"], 2)

            cur = upsert_sync_cursor(
                db,
                tenant,
                SyncCursorUpsertIn(
                    connection_ref="hubspot-main",
                    stream_name="contacts",
                    cursor_value="cur-2026-11",
                    synced_count=42,
                ),
                now=T1,
            )
            self.assertEqual(cur["synced_count"], 42)
            self.assertEqual(len(list_sync_cursors(db, tenant)), 1)

    def test_privacy_export_and_erasure_inventory_attachments_memory_webchat_and_workflows(self):
        tenant = self._seed_tenant("tenant_p5_priv", 9405)
        limiter = IngestRateLimiter(redis_client=None, window_seconds=60)

        with tempfile.TemporaryDirectory() as tmp_name:
            tmp_dir = Path(tmp_name)
            with Session(self.engine) as db:
                widget = create_webchat_widget(
                    db,
                    tenant,
                    WebchatWidgetCreateIn(name="Privacy Widget", allowed_origins=["https://priv.example"]),
                    actor_user_id="mgr-1",
                    now=T0,
                )
                wait_wf = create_workflow(
                    db,
                    tenant,
                    WorkflowCreateIn(
                        name="Privacy Wait WF",
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

                wc_session = create_webchat_session(
                    db,
                    widget_key=widget["widget_key"],
                    origin="https://priv.example",
                    visitor_name="Priv Visitor",
                    visitor_email="priv@example.test",
                    limiter=limiter,
                    now=T0,
                )
                process_tenant_workflows(db, tenant, now=T0)
                self.assertEqual(list_workflow_runs(db, tenant, workflow_id=wait_wf["id"])[0]["status"], "waiting")

                bind_tenant_session(db, tenant.schema_name)
                wc_row = db.scalar(
                    select(WebchatSession).where(WebchatSession.conversation_id == wc_session["conversation_id"])
                )
                client_row = db.scalar(select(Cliente).where(Cliente.id == wc_row.client_id))
                conv_id = wc_session["conversation_id"]
                wa_id = client_row.whatsapp_id

                db.add(Message(whatsapp_id=wa_id, rol="usuario", direction="inbound", mensaje="Dato sensible 123"))
                db.add(
                    ConversationMemoryItem(
                        conversation_id=conv_id,
                        memory_key="budget",
                        memory_value="5000 USD",
                        source_type="operator",
                        source_ref="msg-1",
                        expires_at=T1 + timedelta(days=7),
                    )
                )
                priv_case = SolicitudDerecho(
                    tipo_derecho="eliminacion",
                    whatsapp_id=wa_id,
                    estado="en_proceso",
                )
                db.add(priv_case)
                db.commit()
                db.refresh(priv_case)

                att = upload_private_attachment_bytes(
                    db,
                    tenant,
                    resource_type="contact",
                    resource_id=client_row.id,
                    filename="dni.txt",
                    content_type="text/plain",
                    data=b"SENSITIVE_BYTES",
                    uploaded_by="dpo-1",
                    storage_dir=tmp_dir,
                    now=T0,
                )
                storage_file = tmp_dir / att["storage_key"]
                self.assertTrue(storage_file.exists())

                upsert_external_mapping(
                    db,
                    tenant,
                    ExternalMappingUpsertIn(
                        connection_ref="crm-ext",
                        resource_type="contact",
                        remote_id="ext-priv-1",
                        local_type="contact",
                        local_id=str(client_row.id),
                    ),
                    now=T0,
                )

                exported = export_privacy_case_data(db, tenant, priv_case.id, actor_id="dpo-1")
                self.assertEqual(len(exported["memory_items"]), 1)
                self.assertEqual(len(exported["attachments"]), 1)
                self.assertGreaterEqual(exported["webchat_sessions_count"], 1)
                self.assertGreaterEqual(exported["external_mappings_count"], 1)
                self.assertGreaterEqual(exported["workflow_runs_count"], 1)

                erased = execute_privacy_erasure(
                    db,
                    tenant,
                    priv_case.id,
                    actor_id="dpo-1",
                    confirmed=True,
                    storage_dir=tmp_dir,
                )
                self.assertEqual(erased["memory_items_deleted"], 1)
                self.assertEqual(erased["attachments_deleted"], 1)
                self.assertEqual(erased["webchat_sessions_anonymized"], 1)
                self.assertEqual(erased["workflow_runs_cancelled"], 1)
                self.assertFalse(storage_file.exists())

                bind_tenant_session(db, tenant.schema_name)
                self.assertEqual(db.scalar(select(func.count()).select_from(ConversationMemoryItem)), 0)
                self.assertEqual(db.scalar(select(func.count()).select_from(PrivateAttachment)), 0)
                wc_after = db.scalar(
                    select(WebchatSession).where(WebchatSession.conversation_id == wc_session["conversation_id"])
                )
                self.assertEqual(wc_after.visitor_name, "Anonimizado")
                self.assertEqual(wc_after.status, "closed")
                self.assertEqual(list_workflow_runs(db, tenant, workflow_id=wait_wf["id"])[0]["status"], "cancelled")
                self.assertGreaterEqual(db.scalar(select(func.count()).select_from(ContactSuppression)), 1)
