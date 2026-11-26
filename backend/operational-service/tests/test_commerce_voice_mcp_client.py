import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant_resolver import TenantContext
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.commerce import CommerceOrderCreateIn, CommerceRefundIn
from app.schemas.integrations import ChannelWebhookRouteCreateIn
from app.schemas.mcp_client import RemoteMcpInvokeIn, RemoteMcpServerCreateIn
from app.schemas.voice import (
    VoiceCallCompleteIn,
    VoiceCallCreateIn,
    VoiceCallSegmentIn,
    VoiceCallTransferIn,
)
from app.schemas.workflow import WorkflowCreateIn, WorkflowGraphIn
from app.services.analytics_service import analytics_kpis
from app.services.capture_service import issue_scoped_credential
from app.services.commerce_service import create_checkout_link, create_commerce_order, list_order_events, record_commerce_refund
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.integrations_service import create_webhook_route
from app.services.mcp_client_service import (
    discover_remote_mcp_tools,
    invoke_remote_mcp_tool,
    register_remote_mcp_server,
    revoke_remote_mcp_server,
)
from app.services.privacy_case_service import execute_privacy_erasure, export_privacy_case_data
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.voice_service import (
    append_voice_segment,
    complete_voice_call,
    get_voice_call,
    start_voice_call,
    transfer_voice_call,
)
from app.services.workflow_service import create_workflow, list_workflow_runs, process_tenant_workflows, publish_workflow
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.operations import Cliente, Lead, Message, SolicitudDerecho
from app.tenant_models.phase4_hub import ToolInvocation
from app.tenant_models.phase6_extensions import VoiceCallSegment, VoiceCallSession
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 26, 20, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=8)


def _shopify_hmac(secret: str, raw: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest()).decode("ascii")


def _mp_sig(secret: str, data_id: str, req_id: str, ts: str = "1732651200") -> str:
    manifest = f"id:{data_id};request-id:{req_id};ts:{ts};"
    digest = hmac.new(secret.encode("utf-8"), manifest.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"ts={ts},v1={digest}"


class CommerceVoiceMcpClientTests(PostgresCase):
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

    def test_commerce_signed_webhooks_discrepancies_refunds_and_kpis(self):
        tenant = self._seed_tenant("tenant_p6_comm", 9501)
        self._override_db()

        with Session(self.engine) as db:
            create_webhook_route(
                db,
                tenant,
                ChannelWebhookRouteCreateIn(
                    channel="shopify",
                    external_account_id="acme.myshopify.com",
                    verify_token="shop_verify_tok_123",
                    app_secret="shopify_secret_key_1",
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            create_webhook_route(
                db,
                tenant,
                ChannelWebhookRouteCreateIn(
                    channel="mercadopago",
                    external_account_id="mp-acct-1",
                    verify_token="mp_verify_tok_123",
                    app_secret="mp_secret_key_1",
                ),
                actor_user_id="mgr-1",
                now=T0,
            )

            ord_mp = create_commerce_order(
                db,
                tenant,
                CommerceOrderCreateIn(provider="mercadopago", currency="clp", expected_amount_minor=25000),
                actor_user_id="mgr-1",
                now=T0,
            )
            ord_mp = create_checkout_link(db, tenant, ord_mp["id"], actor_user_id="mgr-1", now=T0)
            self.assertEqual(ord_mp["status"], "checkout_created")
            self.assertIn(ord_mp["order_number"], ord_mp["checkout_url"])

            ord_shop = create_commerce_order(
                db,
                tenant,
                CommerceOrderCreateIn(
                    provider="shopify",
                    external_order_id="sh-1001",
                    currency="USD",
                    expected_amount_minor=12000,
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            ord_mismatch = create_commerce_order(
                db,
                tenant,
                CommerceOrderCreateIn(
                    provider="shopify",
                    external_order_id="sh-1002",
                    currency="USD",
                    expected_amount_minor=5000,
                ),
                actor_user_id="mgr-1",
                now=T0,
            )

        client = TestClient(app)

        # Bad Shopify HMAC signature returns 401.
        sh_body = json.dumps({"id": "sh-1001", "currency": "USD", "amount_minor": 12000}).encode("utf-8")
        bad_sh = client.post(
            "/api/v1/public/webhooks/commerce/shopify",
            content=sh_body,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Shop-Domain": "acme.myshopify.com",
                "X-Shopify-Webhook-Id": "wh-sh-1",
                "X-Shopify-Topic": "orders/paid",
                "X-Shopify-Hmac-Sha256": "invalid==",
            },
        )
        self.assertEqual(bad_sh.status_code, 401)

        # Valid Shopify confirmation + duplicate replay dedup.
        good_sh = client.post(
            "/api/v1/public/webhooks/commerce/shopify",
            content=sh_body,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Shop-Domain": "acme.myshopify.com",
                "X-Shopify-Webhook-Id": "wh-sh-1",
                "X-Shopify-Topic": "orders/paid",
                "X-Shopify-Hmac-Sha256": _shopify_hmac("shopify_secret_key_1", sh_body),
            },
        )
        self.assertEqual(good_sh.status_code, 200)
        self.assertEqual(good_sh.json()["data"]["status"], "paid")

        dup_sh = client.post(
            "/api/v1/public/webhooks/commerce/shopify",
            content=sh_body,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Shop-Domain": "acme.myshopify.com",
                "X-Shopify-Webhook-Id": "wh-sh-1",
                "X-Shopify-Topic": "orders/paid",
                "X-Shopify-Hmac-Sha256": _shopify_hmac("shopify_secret_key_1", sh_body),
            },
        )
        self.assertEqual(dup_sh.status_code, 200)
        self.assertTrue(dup_sh.json()["data"]["duplicate"])

        # Amount mismatch on sh-1002 flags discrepancy without confirming revenue.
        mismatch_body = json.dumps({"id": "sh-1002", "currency": "USD", "amount_minor": 100}).encode("utf-8")
        mismatch_res = client.post(
            "/api/v1/public/webhooks/commerce/shopify",
            content=mismatch_body,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Shop-Domain": "acme.myshopify.com",
                "X-Shopify-Webhook-Id": "wh-sh-2",
                "X-Shopify-Topic": "orders/paid",
                "X-Shopify-Hmac-Sha256": _shopify_hmac("shopify_secret_key_1", mismatch_body),
            },
        )
        self.assertEqual(mismatch_res.status_code, 200)
        self.assertEqual(mismatch_res.json()["data"]["status"], "discrepancy")
        self.assertEqual(mismatch_res.json()["data"]["confirmed_amount_minor"], 0)

        # Mercado Pago signed webhook + bad signature 401.
        mp_payload = {
            "data": {"id": "mp-pay-77"},
            "external_reference": ord_mp["order_number"],
            "status": "approved",
            "currency_id": "CLP",
            "transaction_amount_minor": 25000,
        }
        bad_mp = client.post(
            "/api/v1/public/webhooks/commerce/mercadopago",
            params={"account_id": "mp-acct-1"},
            json=mp_payload,
            headers={"x-signature": "ts=1,v1=deadbeef", "x-request-id": "mp-req-1"},
        )
        self.assertEqual(bad_mp.status_code, 401)

        good_mp = client.post(
            "/api/v1/public/webhooks/commerce/mercadopago",
            params={"account_id": "mp-acct-1"},
            json=mp_payload,
            headers={"x-signature": _mp_sig("mp_secret_key_1", "mp-pay-77", "mp-req-1"), "x-request-id": "mp-req-1"},
        )
        self.assertEqual(good_mp.status_code, 200)
        self.assertEqual(good_mp.json()["data"]["status"], "paid")

        # Partial refund + over-refund guard 422 + KPI isolation by currency.
        with Session(self.engine) as db:
            ref_res = record_commerce_refund(
                db,
                tenant,
                ord_mp["id"],
                CommerceRefundIn(amount_minor=5000, external_event_id="ref-mp-1"),
                actor_user_id="mgr-1",
                now=T1,
            )
            self.assertEqual(ref_res["status"], "partially_refunded")
            self.assertEqual(ref_res["net_confirmed_minor"], 20000)

            with self.assertRaises(HTTPException) as over_err:
                record_commerce_refund(
                    db,
                    tenant,
                    ord_mp["id"],
                    CommerceRefundIn(amount_minor=25000, external_event_id="ref-mp-over"),
                    actor_user_id="mgr-1",
                    now=T1,
                )
            self.assertEqual(over_err.exception.status_code, 422)

            events = list_order_events(db, tenant, ord_mp["id"])
            self.assertEqual([ev["amount_minor"] for ev in events], [25000, -5000])

            kpis = analytics_kpis(db, tenant)
            self.assertEqual(kpis.commerce.total_orders, 3)
            self.assertEqual(kpis.commerce.paid_orders, 2)
            self.assertEqual(kpis.commerce.discrepancy_orders, 1)
            self.assertEqual(kpis.commerce.confirmed_net_by_currency, {"CLP": 20000, "USD": 12000})

    def test_voice_sessions_barge_in_twilio_webhook_kpis_and_privacy(self):
        tenant_a = self._seed_tenant("tenant_p6_voice_a", 9502)
        tenant_b = self._seed_tenant("tenant_p6_voice_b", 9503)
        self._override_db()

        with Session(self.engine) as db:
            create_webhook_route(
                db,
                tenant_a,
                ChannelWebhookRouteCreateIn(
                    channel="voice_twilio",
                    external_account_id="AC_A",
                    verify_token="tw_verify_tok_123",
                    app_secret="tw_secret_a",
                ),
                actor_user_id="mgr-a",
                now=T0,
            )

            # Publish waiting workflow and start a stub voice call with recording_consent=False.
            wf = create_workflow(
                db,
                tenant_a,
                WorkflowCreateIn(
                    name="Voice Barge-in Cancel WF",
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

            call = start_voice_call(
                db,
                tenant_a,
                VoiceCallCreateIn(
                    provider="stub",
                    external_call_id="call-priv-1",
                    direction="inbound",
                    from_number="+56911112222",
                    to_number="+56220001111",
                    recording_consent=False,
                ),
                now=T0,
            )
            bind_tenant_session(db, tenant_a.schema_name)
            lead = db.scalar(select(Lead).where(Lead.cliente_id == call["client_id"]))
            publish_domain_event_in_tx(
                db,
                tenant_a,
                event_type="lead.created",
                aggregate_type="lead",
                aggregate_id=lead.id,
                payload={"lead_id": lead.id, "contact_id": call["client_id"]},
                occurred_at=T0,
            )
            db.commit()
            process_tenant_workflows(db, tenant_a, now=T0)
            self.assertEqual(list_workflow_runs(db, tenant_a, workflow_id=wf["id"])[0]["status"], "waiting")

            # Caller speaks with barge-in -> cancels wait, mirrors into Message, and deduplicates seq 1.
            seg1 = append_voice_segment(
                db,
                tenant_a,
                call["id"],
                VoiceCallSegmentIn(sequence_no=1, speaker="caller", transcript="Quiero hablar con un asesor", is_barge_in=True),
                now=T0,
            )
            self.assertFalse(seg1["duplicate"])
            seg1_dup = append_voice_segment(
                db,
                tenant_a,
                call["id"],
                VoiceCallSegmentIn(sequence_no=1, speaker="caller", transcript="Quiero hablar con un asesor", is_barge_in=True),
                now=T0,
            )
            self.assertTrue(seg1_dup["duplicate"])
            self.assertEqual(list_workflow_runs(db, tenant_a, workflow_id=wf["id"])[0]["status"], "cancelled")

            # Attempting to attach recording without recording_consent fails 422.
            with self.assertRaises(HTTPException) as rec_err:
                complete_voice_call(
                    db,
                    tenant_a,
                    call["id"],
                    VoiceCallCompleteIn(status="completed", billable_seconds=30, recording_attachment_id=99),
                    now=T1,
                )
            self.assertEqual(rec_err.exception.status_code, 422)

            transferred = transfer_voice_call(
                db,
                tenant_a,
                call["id"],
                VoiceCallTransferIn(reason="caller_requested_human"),
                actor_user_id="mgr-a",
                now=T1,
            )
            self.assertEqual(transferred["status"], "transferred")
            details = get_voice_call(db, tenant_a, call["id"])
            self.assertEqual(details["barge_in_count"], 1)
            self.assertEqual(len(details["segments"]), 1)

        # Signed Twilio webhook test (bad sig 401 + valid creates call in tenant_a only).
        client = TestClient(app)
        tw_payload = {
            "AccountSid": "AC_A",
            "CallSid": "CA_TW_100",
            "Direction": "inbound",
            "From": "+56988887777",
            "To": "+56229990000",
            "CallStatus": "completed",
            "CallDuration": 45,
        }
        tw_raw = json.dumps(tw_payload).encode("utf-8")
        self.assertEqual(
            client.post(
                "/api/v1/public/webhooks/voice/twilio",
                content=tw_raw,
                headers={"Content-Type": "application/json", "X-Twilio-Signature-256": "sha256=bad"},
            ).status_code,
            401,
        )
        tw_sig = "sha256=" + hmac.new(b"tw_secret_a", tw_raw, hashlib.sha256).hexdigest()
        ok_tw = client.post(
            "/api/v1/public/webhooks/voice/twilio",
            content=tw_raw,
            headers={"Content-Type": "application/json", "X-Twilio-Signature-256": tw_sig},
        )
        self.assertEqual(ok_tw.status_code, 200)
        self.assertEqual(ok_tw.json()["data"]["billable_seconds"], 45)

        with Session(self.engine) as db:
            kpis_a = analytics_kpis(db, tenant_a)
            self.assertEqual(kpis_a.voice.total_calls, 2)
            self.assertEqual(kpis_a.voice.completed_calls, 1)
            self.assertEqual(kpis_a.voice.transferred_calls, 1)
            self.assertEqual(kpis_a.voice.total_billable_seconds, 45)

            bind_tenant_session(db, tenant_b.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(VoiceCallSession)), 0)

            # Privacy export & erasure must redact voice segments & numbers.
            bind_tenant_session(db, tenant_a.schema_name)
            subj = db.get(Cliente, call["client_id"])
            p_case = SolicitudDerecho(tipo_derecho="eliminacion", whatsapp_id=subj.whatsapp_id, estado="en_proceso")
            db.add(p_case)
            db.commit()
            db.refresh(p_case)

            exported = export_privacy_case_data(db, tenant_a, p_case.id, actor_id="dpo-1")
            self.assertEqual(exported["voice_calls_count"], 1)

            erased = execute_privacy_erasure(db, tenant_a, p_case.id, actor_id="dpo-1", confirmed=True)
            self.assertEqual(erased["voice_segments_redacted"], 1)

            bind_tenant_session(db, tenant_a.schema_name)
            call_after = db.get(VoiceCallSession, call["id"])
            seg_after = db.scalar(select(VoiceCallSegment).where(VoiceCallSegment.call_id == call["id"]))
            self.assertEqual(call_after.from_number, "[REDACTED]")
            self.assertEqual(seg_after.transcript, "[REDACTED_PRIVACY]")

    def test_bidirectional_remote_mcp_client_ssrf_allowlist_idempotency_and_revocation(self):
        tenant = self._seed_tenant("tenant_p6_rmcp", 9504)
        self._override_db()

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(id=1, rut="rut-r1", nombre="Antes", email="r1@example.test", whatsapp_id="56960001"))
            db.commit()

            # SSRF URL rejection checks.
            for bad_url in ("http://public.example/mcp", "https://localhost:8001/mcp", "https://127.0.0.1/mcp", "https://10.0.0.5/mcp"):
                with self.assertRaises(HTTPException) as err:
                    register_remote_mcp_server(
                        db,
                        tenant,
                        RemoteMcpServerCreateIn(server_key="bad-srv", name="Bad", base_url=bad_url, allowed_tools=["x"]),
                        now=T0,
                    )
                self.assertEqual(err.exception.status_code, 422)

            scoped = issue_scoped_credential(
                db,
                tenant,
                name="two-way-mcp",
                scopes=["mcp:read", "mcp:invoke"],
                created_by="mgr-1",
            )
            server = register_remote_mcp_server(
                db,
                tenant,
                RemoteMcpServerCreateIn(
                    server_key="kron-peer",
                    name="KronFlow Peer MCP",
                    base_url="https://mcp.partner.example/api/v1/mcp",
                    auth_header_name="X-Flowkron-Key",
                    auth_token=scoped["api_key"],
                    allowed_tools=["crm.contact.rename"],
                ),
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertIsNotNone(server["auth_fingerprint"])
            self.assertNotIn("auth_token", server)

            # Bidirectional transport routing client calls to KronFlow's real /api/v1/mcp server.
            http_client = TestClient(app)
            call_counter = {"count": 0}

            def peer_transport(_url: str, headers: dict[str, str], body: dict):
                call_counter["count"] += 1
                resp = http_client.post("/api/v1/mcp", headers=headers, json=body)
                return resp.json()

            discovered = discover_remote_mcp_tools(db, tenant, server["id"], transport=peer_transport, now=T0)
            self.assertTrue(any(t["name"] == "crm.contact.rename" for t in discovered["discovered_tools"]))

            # Unlisted tool blocked with 403 before contacting server.
            with self.assertRaises(HTTPException) as unlisted_err:
                invoke_remote_mcp_tool(
                    db,
                    tenant,
                    server["id"],
                    RemoteMcpInvokeIn(
                        tool_name="crm.lead.update_stage",
                        arguments={"resource_id": 1, "stage": "ganado"},
                        idempotency_key="rmcp-unlisted-1",
                    ),
                    actor_user_id="mgr-1",
                    transport=peer_transport,
                    now=T0,
                )
            self.assertEqual(unlisted_err.exception.status_code, 403)

            calls_before_invoke = call_counter["count"]
            res1 = invoke_remote_mcp_tool(
                db,
                tenant,
                server["id"],
                RemoteMcpInvokeIn(
                    tool_name="crm.contact.rename",
                    arguments={"resource_id": 1, "name": "Renombrado Via MCP"},
                    idempotency_key="rmcp-rename-1",
                ),
                actor_user_id="mgr-1",
                transport=peer_transport,
                now=T0,
            )
            self.assertFalse(res1["duplicate"])
            self.assertEqual(res1["result"]["_meta"]["status"], "proposed")

            # Repeated idempotency key does NOT re-invoke transport.
            res2 = invoke_remote_mcp_tool(
                db,
                tenant,
                server["id"],
                RemoteMcpInvokeIn(
                    tool_name="crm.contact.rename",
                    arguments={"resource_id": 1, "name": "Renombrado Via MCP"},
                    idempotency_key="rmcp-rename-1",
                ),
                actor_user_id="mgr-1",
                transport=peer_transport,
                now=T1,
            )
            self.assertTrue(res2["duplicate"])
            self.assertEqual(call_counter["count"], calls_before_invoke + 1)

            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(AIActionProposal)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(ToolInvocation)), 2)

            revoke_remote_mcp_server(db, tenant, server["id"], actor_user_id="mgr-1", now=T1)
            with self.assertRaises(HTTPException) as rev_err:
                invoke_remote_mcp_tool(
                    db,
                    tenant,
                    server["id"],
                    RemoteMcpInvokeIn(
                        tool_name="crm.contact.rename",
                        arguments={"resource_id": 1, "name": "Otra"},
                        idempotency_key="rmcp-rename-2",
                    ),
                    actor_user_id="mgr-1",
                    transport=peer_transport,
                    now=T1,
                )
            self.assertEqual(rev_err.exception.status_code, 403)
