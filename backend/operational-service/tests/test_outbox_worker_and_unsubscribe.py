from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.rate_limit import IngestRateLimiter
from app.core.tenant_resolver import TenantContext
from app.main import readyz
from app.public_models.tenant_runtime import TenantRuntime
from app.services.action_outbox_service import begin_outbox_execution, claim_next_outbox_jobs, complete_outbox_action
from app.services.ai_extensions_service import enqueue_external_notification
from app.services.campaign_service import (
    approve_campaign,
    create_campaign,
    create_template_with_version,
    issue_unsubscribe_token,
    promote_due_scheduled_campaigns,
    redeem_unsubscribe_token,
)
from app.services.channel_connection_service import (
    create_channel_connection,
    revoke_channel_connection,
    send_conversation_email,
)
from app.services.consent_authorization_service import evaluate_persisted_consent, record_consent_decision
from app.services.conversation_control_service import claim_conversation, send_human_reply
from app.services.domain_event_service import replay_domain_events
from app.services.outbox_dispatcher import TransportResult, dispatch_tenant_outbox_batch, run_worker_cycle
from app.services.post_v1_service import create_webhook_subscription, enqueue_webhook_delivery, sign_webhook_payload
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.ai_extensions import ExternalNotificationDelivery
from app.tenant_models.campaigns import Campaign, CampaignRecipient, DeliveryAttempt
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.operations import Cliente, Conversation, Message
from app.tenant_models.post_v1 import WebhookDelivery
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=10)
T2 = T0 + timedelta(minutes=20)


class FakeOutboxTransport:
    def __init__(self):
        self.email_calls = []
        self.whatsapp_calls = []
        self.webhook_calls = []
        self.email_responses = []
        self.whatsapp_responses = []
        self.webhook_responses = []

    def can_send_email(self) -> bool:
        return True

    def can_send_whatsapp(self) -> bool:
        return True

    def send_email(self, **kwargs) -> TransportResult:
        self.email_calls.append(kwargs)
        if self.email_responses:
            return self.email_responses.pop(0)
        return TransportResult(200, body={"message_id": f"msg-{len(self.email_calls)}", "status": "accepted"})

    def send_whatsapp_human_reply(self, **kwargs) -> TransportResult:
        self.whatsapp_calls.append(kwargs)
        if self.whatsapp_responses:
            return self.whatsapp_responses.pop(0)
        return TransportResult(200, body={"status": "sent", "provider_message_id": f"wa-{len(self.whatsapp_calls)}"})

    def deliver_webhook(self, **kwargs) -> TransportResult:
        self.webhook_calls.append(kwargs)
        if self.webhook_responses:
            return self.webhook_responses.pop(0)
        return TransportResult(200, body={"ok": True})


class OutboxWorkerAndUnsubscribeTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int) -> TenantContext:
        tenant = TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="starter",
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
                    plan="starter",
                    status="active",
                )
            )
            db.commit()
        return tenant

    def test_scheduled_campaign_promotion_and_blocked_connection(self):
        tenant = self._seed_tenant("tenant_sched_camp", 4101)
        with Session(self.engine) as db:
            conn_ok = create_channel_connection(
                db, tenant, channel="email", provider="stub", sender_address="ok@acme.test",
                display_name="OK", verified=True, sandbox_only=True, actor_user_id="admin", now=T0,
            )
            conn_bad = create_channel_connection(
                db, tenant, channel="email", provider="stub", sender_address="bad@acme.test",
                display_name="Bad", verified=True, sandbox_only=True, actor_user_id="admin", now=T0,
            )
            tmpl = create_template_with_version(
                db, tenant, name="Sched", channel="email", subject="Hola", body_text="Texto",
                approve_immediately=True, actor_user_id="admin", now=T0,
            )
            c1 = create_campaign(
                db, tenant, name="Due OK", channel="email", purpose="marketing",
                template_version_id=tmpl["template_version_id"], connection_id=conn_ok["id"],
                actor_user_id="admin", now=T0,
            )
            c2 = create_campaign(
                db, tenant, name="Due Revoked", channel="email", purpose="marketing",
                template_version_id=tmpl["template_version_id"], connection_id=conn_bad["id"],
                actor_user_id="admin", now=T0,
            )
            approve_campaign(db, tenant, c1["id"], expected_version=1, actor_user_id="admin", scheduled_at=T1, now=T0)
            approve_campaign(db, tenant, c2["id"], expected_version=1, actor_user_id="admin", scheduled_at=T1, now=T0)
            revoke_channel_connection(db, tenant, conn_bad["id"], actor_user_id="admin", now=T0)

            self.assertEqual(promote_due_scheduled_campaigns(db, tenant, now=T0 + timedelta(minutes=5)), 0)
            self.assertEqual(promote_due_scheduled_campaigns(db, tenant, now=T1), 1)

            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.get(Campaign, c1["id"]).status, "running")
            self.assertEqual(db.get(Campaign, c2["id"]).status, "paused")
            events = replay_domain_events(db, tenant, event_types=["campaign.started"])["items"]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["aggregate_id"], str(c1["id"]))

    def test_worker_dispatches_all_five_outbox_types_with_failures_and_retries(self):
        tenant = self._seed_tenant("tenant_worker_all", 4102)
        settings = Settings(mail_sender_key="flowkron", worker_allow_stub_dispatch=True)
        transport = FakeOutboxTransport()

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add_all([
                Cliente(id=1, rut="r1", nombre="Uno", email="uno@example.test", whatsapp_id="56911110001", consentimiento_datos=True),
                Cliente(id=2, rut="r2", nombre="Dos", email="dos@example.test"),
                Cliente(id=3, rut="r3", nombre="Tres", email="tres@example.test"),
                Conversation(id=1, session_id="56911110001", message={"channel": "whatsapp"}),
            ])
            db.flush()
            db.add_all([
                ContactPoint(id=1, client_id=1, point_type="email", normalized_value="uno@example.test", status="active", verified=True),
                ContactPoint(id=2, client_id=2, point_type="email", normalized_value="dos@example.test", status="active", verified=True),
                ContactPoint(id=3, client_id=3, point_type="email", normalized_value="tres@example.test", status="active", verified=True),
            ])
            db.commit()

            for cid, addr in ((1, "uno@example.test"), (2, "dos@example.test"), (3, "tres@example.test")):
                record_consent_decision(
                    db, tenant, client_id=cid, channel="email", destination=addr,
                    purpose="marketing", granted=True, effective_at=T0, recorded_at=T0, source="form",
                )

            conn = create_channel_connection(
                db, tenant, channel="email", provider="resend", sender_address="news@acme.test",
                display_name="Acme Resend", verified=True, sandbox_only=False, provider_secret="re_live",
                actor_user_id="admin", now=T0,
            )
            tmpl = create_template_with_version(
                db, tenant, name="Camp", channel="email", subject="Hola {{name}}",
                body_text="Mensaje para {{name}}", declared_variables=["name"],
                approve_immediately=True, actor_user_id="admin", now=T0,
            )
            camp = create_campaign(
                db, tenant, name="Resend Camp", channel="email", purpose="marketing",
                template_version_id=tmpl["template_version_id"], connection_id=conn["id"],
                actor_user_id="admin", now=T0,
            )
            approve_campaign(db, tenant, camp["id"], expected_version=1, actor_user_id="admin", now=T0)

            # Conversation email (FK-23)
            conv_email = send_conversation_email(
                db, tenant, 1, connection_id=conn["id"], to_email="uno@example.test",
                subject="Seguimiento", body_text="Hola desde CRM", idempotency_key="ce-1",
                actor_user_id="op-1", now=T0,
            )

            # HITL human reply (FK-06)
            claim_conversation(db, tenant, 1, actor_user_id="op-1", expected_version=1, now=T0)
            human_reply = send_human_reply(
                db, tenant, 1, actor_user_id="op-1", body="Te respondo por WhatsApp",
                idempotency_key="hr-1", now=T0,
            )

            # Webhooks (FK-11): 1 failing -> dead_letter, 1 succeeding
            sub = create_webhook_subscription(
                db, tenant, name="CRM", target_url="https://hooks.partner.example/in",
                event_types=["lead.captured"], max_attempts=2, actor_user_id="admin", now=T0,
            )
            wh_retry = enqueue_webhook_delivery(
                db, tenant, sub["id"], event_id="evt_retry", event_type="lead.captured", payload={"id": 1}, now=T0,
            )
            wh_ok = enqueue_webhook_delivery(
                db, tenant, sub["id"], event_id="evt_ok", event_type="lead.captured", payload={"id": 2}, now=T0,
            )

            # Notifications (FK-25)
            n_stub = enqueue_external_notification(
                db, tenant, dedup_key="n-stub-1", event_type="handoff", channel="webhook_stub",
                recipient="stub://ops", payload={"c": 1}, actor_user_id="sys", now=T0,
            )
            n_email = enqueue_external_notification(
                db, tenant, dedup_key="n-email-1", event_type="handoff", channel="email",
                recipient="ops@acme.test", payload={"c": 1}, actor_user_id="sys", now=T0,
            )

            # Configure transport responses in FIFO order for emails:
            # 1: campaign uno -> 200
            # 2: campaign dos -> 422 definitive failure
            # 3: campaign tres -> timeout (unknown, never blind-retried)
            # 4: conv email -> 200
            # 5: notif email -> 200
            transport.email_responses = [
                TransportResult(200, body={"message_id": "re-camp-1", "status": "accepted"}),
                TransportResult(422, error="invalid_recipient"),
                TransportResult(None, error="read_timeout", definitely_not_sent=False),
                TransportResult(200, body={"message_id": "re-conv-1", "status": "accepted"}),
                TransportResult(200, body={"message_id": "re-notif-1", "status": "accepted"}),
            ]
            # WhatsApp human reply: disconnected first -> retryable pending, then 200 on second batch
            transport.whatsapp_responses = [
                TransportResult(409, body={"error": "session_not_connected", "sent": False, "retryable": True}, error="session_not_connected", definitely_not_sent=True),
                TransportResult(200, body={"status": "sent", "provider_message_id": "wa-human-99"}),
            ]
            # Webhooks: wh_retry 503 then 503 (dead_letter), wh_ok 200
            transport.webhook_responses = [
                TransportResult(503, error="http_503"),
                TransportResult(200, body={"ok": True}),
                TransportResult(503, error="http_503"),
            ]

            with patch("app.services.outbox_dispatcher.validate_webhook_target_with_dns", side_effect=lambda u: u):
                batch1 = dispatch_tenant_outbox_batch(db, tenant, settings=settings, transport=transport, limit=20, now=T0)
                self.assertEqual(batch1["claimed"], 9)
                self.assertEqual(batch1["completed"], 5)
                self.assertEqual(batch1["failed"], 1)
                self.assertEqual(batch1["unknown"], 1)
                self.assertEqual(batch1["retried"], 2)

                # Advance past backoff for retryable human_reply (30s) and webhook (30s).
                batch2 = dispatch_tenant_outbox_batch(
                    db, tenant, settings=settings, transport=transport, limit=20, now=T0 + timedelta(seconds=35),
                )
                self.assertEqual(batch2["claimed"], 2)
                self.assertEqual(batch2["completed"], 1)
                self.assertEqual(batch2["failed"], 1)

            bind_tenant_session(db, tenant.schema_name)
            r1 = db.scalar(select(CampaignRecipient).where(CampaignRecipient.destination == "uno@example.test"))
            r2 = db.scalar(select(CampaignRecipient).where(CampaignRecipient.destination == "dos@example.test"))
            r3 = db.scalar(select(CampaignRecipient).where(CampaignRecipient.destination == "tres@example.test"))
            self.assertEqual((r1.status, r1.provider_message_id), ("accepted", "re-camp-1"))
            self.assertEqual(r2.status, "failed")
            self.assertEqual(r3.status, "unknown")
            self.assertEqual(db.get(ActionOutboxJob, r3.outbox_job_id).state, "unknown")
            self.assertEqual(db.query(DeliveryAttempt).count(), 3)

            m_email = db.get(Message, conv_email["message_id"])
            m_human = db.get(Message, human_reply["message_id"])
            self.assertEqual((m_email.provider_message_id, m_email.delivery_status), ("re-conv-1", "sent"))
            self.assertEqual((m_human.provider_message_id, m_human.delivery_status), ("wa-human-99", "sent"))

            self.assertEqual(db.get(WebhookDelivery, wh_retry["id"]).status, "dead_letter")
            self.assertEqual(db.get(WebhookDelivery, wh_ok["id"]).status, "delivered")
            self.assertEqual(
                transport.webhook_calls[0]["signature"],
                sign_webhook_payload(sub["signing_secret"], "evt_retry", {"id": 1}),
            )

            dn_stub = db.get(ExternalNotificationDelivery, n_stub["id"])
            dn_email = db.get(ExternalNotificationDelivery, n_email["id"])
            self.assertEqual(dn_stub.status, "delivered")
            self.assertEqual((dn_email.status, dn_email.receipt_ref), ("delivered", "re-notif-1"))

    def test_human_reply_cancelled_when_consent_withdrawn_before_dispatch(self):
        tenant = self._seed_tenant("tenant_hr_baja", 4103)
        transport = FakeOutboxTransport()
        settings = Settings()

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add_all([
                Cliente(id=1, rut="r1", nombre="Baja", whatsapp_id="56922220001", consentimiento_datos=True),
                Conversation(id=1, session_id="56922220001", message={"channel": "whatsapp"}),
            ])
            db.commit()
            claim_conversation(db, tenant, 1, actor_user_id="op-1", expected_version=1, now=T0)
            queued = send_human_reply(db, tenant, 1, actor_user_id="op-1", body="Hola", idempotency_key="hr-baja", now=T0)

            bind_tenant_session(db, tenant.schema_name)
            db.get(Cliente, 1).consentimiento_datos = False
            db.commit()

            res = dispatch_tenant_outbox_batch(db, tenant, settings=settings, transport=transport, now=T0)
            self.assertEqual(res["suppressed"], 1)
            self.assertEqual(transport.whatsapp_calls, [])

            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.get(ActionOutboxJob, queued["outbox_job_id"]).state, "cancelled")
            self.assertEqual(db.get(Message, queued["message_id"]).delivery_status, "failed")

    def test_self_service_unsubscribe_token_cancels_pending_and_preserves_executing_and_completed(self):
        tenant = self._seed_tenant("tenant_unsub_tok", 4104)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add_all([
                Cliente(id=1, rut="r1", nombre="Pendiente", email="pend@example.test"),
                Cliente(id=2, rut="r2", nombre="Ejecutando", email="exec@example.test"),
                Cliente(id=3, rut="r3", nombre="Completado", email="done@example.test"),
            ])
            db.flush()
            db.add_all([
                ContactPoint(id=1, client_id=1, point_type="email", normalized_value="pend@example.test", status="active", verified=True),
                ContactPoint(id=2, client_id=2, point_type="email", normalized_value="exec@example.test", status="active", verified=True),
                ContactPoint(id=3, client_id=3, point_type="email", normalized_value="done@example.test", status="active", verified=True),
            ])
            db.commit()

            for cid, addr in ((1, "pend@example.test"), (2, "exec@example.test"), (3, "done@example.test")):
                record_consent_decision(
                    db, tenant, client_id=cid, channel="email", destination=addr,
                    purpose="marketing", granted=True, effective_at=T0, recorded_at=T0, source="form",
                )

            conn = create_channel_connection(
                db, tenant, channel="email", provider="stub", sender_address="news@acme.test",
                display_name="News", verified=True, sandbox_only=True, actor_user_id="admin", now=T0,
            )
            tmpl = create_template_with_version(
                db, tenant, name="T", channel="email", subject="S", body_text="B",
                approve_immediately=True, actor_user_id="admin", now=T0,
            )
            camp = create_campaign(
                db, tenant, name="C", channel="email", purpose="marketing",
                template_version_id=tmpl["template_version_id"], connection_id=conn["id"],
                actor_user_id="admin", now=T0,
            )
            approve_campaign(db, tenant, camp["id"], expected_version=1, actor_user_id="admin", now=T0)

            # Move job for exec@ to executing, and job for done@ to completed; leave pend@ pending.
            claimed = claim_next_outbox_jobs(db, tenant, action_types=["campaign.delivery.send"], limit=3, now=T0)
            jobs_by_dest = {j.payload["destination"]: j for j in claimed}
            begin_outbox_execution(db, tenant, jobs_by_dest["exec@example.test"].id, jobs_by_dest["exec@example.test"].claim_token, now=T0)
            complete_outbox_action(db, tenant, jobs_by_dest["done@example.test"].id, jobs_by_dest["done@example.test"].claim_token, effect_reference="ok", now=T0)
            # Release pend@ back to pending (or keep claimed; both pending and claimed must be cancelled).
            bind_tenant_session(db, tenant.schema_name)
            pend_job = db.get(ActionOutboxJob, jobs_by_dest["pend@example.test"].id)
            pend_job.state = "pending"
            pend_job.claim_token = None
            pend_job.lease_until = None
            db.commit()

            tok_pend = issue_unsubscribe_token(
                db, tenant, channel="email", destination="pend@example.test", purpose="marketing", client_id=1, ttl_days=30, now=T0,
            )
            tok_exec = issue_unsubscribe_token(
                db, tenant, channel="email", destination="exec@example.test", purpose="marketing", client_id=2, ttl_days=30, now=T0,
            )
            tok_expired = issue_unsubscribe_token(
                db, tenant, channel="email", destination="done@example.test", purpose="marketing", client_id=3, ttl_days=1, now=T0,
            )

            self.assertEqual(redeem_unsubscribe_token(db, tok_pend["token"], now=T1), {"status": "unsubscribed"})
            # Idempotent re-redemption.
            self.assertEqual(redeem_unsubscribe_token(db, tok_pend["token"], now=T1), {"status": "unsubscribed"})
            self.assertEqual(redeem_unsubscribe_token(db, tok_exec["token"], now=T1), {"status": "unsubscribed"})

            with self.assertRaises(HTTPException) as ctx_missing:
                redeem_unsubscribe_token(db, "unsub_invalid", now=T1)
            self.assertEqual(ctx_missing.exception.status_code, 404)

            with self.assertRaises(HTTPException) as ctx_exp:
                redeem_unsubscribe_token(db, tok_expired["token"], now=T0 + timedelta(days=2))
            self.assertEqual(ctx_exp.exception.status_code, 404)

            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.get(ActionOutboxJob, jobs_by_dest["pend@example.test"].id).state, "cancelled")
            self.assertEqual(db.get(ActionOutboxJob, jobs_by_dest["exec@example.test"].id).state, "executing")
            self.assertEqual(db.get(ActionOutboxJob, jobs_by_dest["done@example.test"].id).state, "completed")
            rec_pend = db.scalar(select(CampaignRecipient).where(CampaignRecipient.destination == "pend@example.test"))
            self.assertEqual(rec_pend.status, "suppressed")
            self.assertEqual(
                evaluate_persisted_consent(db, tenant, client_id=1, channel="email", destination="pend@example.test", purpose="marketing", now=T1),
                "suppressed",
            )

    def test_run_worker_cycle_isolates_multiple_tenants(self):
        tenant_a = self._seed_tenant("tenant_cyc_a", 4105)
        tenant_b = self._seed_tenant("tenant_cyc_b", 4106)
        with Session(self.engine) as db:
            na = enqueue_external_notification(
                db, tenant_a, dedup_key="ka", event_type="e", channel="webhook_stub",
                recipient="stub://a", payload={}, actor_user_id="sys", now=T0,
            )
            nb = enqueue_external_notification(
                db, tenant_b, dedup_key="kb", event_type="e", channel="webhook_stub",
                recipient="stub://b", payload={}, actor_user_id="sys", now=T0,
            )

        SessionFactory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        summary = run_worker_cycle(SessionFactory, settings=Settings(worker_allow_stub_dispatch=True), now=T0)
        self.assertGreaterEqual(summary["tenants_checked"], 2)
        self.assertEqual(summary["tenants_failed"], 0)
        self.assertEqual(summary["completed"], 2)

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant_a.schema_name)
            self.assertEqual(db.get(ExternalNotificationDelivery, na["id"]).status, "delivered")
            bind_tenant_session(db, tenant_b.schema_name)
            self.assertEqual(db.get(ExternalNotificationDelivery, nb["id"]).status, "delivered")


class RateLimiterAndReadyzTests(unittest.TestCase):
    def test_ingest_rate_limiter_memory_redis_and_fallback(self):
        mem_limiter = IngestRateLimiter("")
        self.assertTrue(mem_limiter.allow("t1", 2, now=100.0))
        self.assertTrue(mem_limiter.allow("t1", 2, now=101.0))
        self.assertFalse(mem_limiter.allow("t1", 2, now=102.0))
        self.assertTrue(mem_limiter.allow("t1", 2, now=161.0))

        class FakePipeline:
            def __init__(self, store, should_fail=False):
                self.store = store
                self.should_fail = should_fail
                self.ops = []

            def zremrangebyscore(self, key, min_s, max_s):
                self.ops.append(("zrem", key, max_s))
                return self

            def zcard(self, key):
                self.ops.append(("zcard", key))
                return self

            def zadd(self, key, mapping):
                self.ops.append(("zadd", key, mapping))
                return self

            def expire(self, key, ttl):
                self.ops.append(("expire", key, ttl))
                return self

            def execute(self):
                if self.should_fail:
                    raise RuntimeError("redis down")
                results = []
                for op in self.ops:
                    if op[0] == "zrem":
                        key, cutoff = op[1], op[2]
                        self.store[key] = [item for item in self.store.get(key, []) if item[1] > cutoff]
                        results.append(0)
                    elif op[0] == "zcard":
                        results.append(len(self.store.get(op[1], [])))
                    elif op[0] == "zadd":
                        key, mapping = op[1], op[2]
                        self.store.setdefault(key, []).extend(mapping.items())
                        results.append(len(mapping))
                    elif op[0] == "expire":
                        results.append(True)
                return results

        class FakeRedis:
            def __init__(self):
                self.store = {}
                self.should_fail = False

            def pipeline(self):
                return FakePipeline(self.store, should_fail=self.should_fail)

        fake_redis = FakeRedis()
        redis_limiter = IngestRateLimiter("redis://unused:6379/0", redis_client=fake_redis)
        self.assertTrue(redis_limiter.allow("t2", 2, now=200.0))
        self.assertTrue(redis_limiter.allow("t2", 2, now=201.0))
        self.assertFalse(redis_limiter.allow("t2", 2, now=202.0))

        # When Redis fails, falls back gracefully to in-memory limiter.
        fake_redis.should_fail = True
        self.assertTrue(redis_limiter.allow("t3", 1, now=203.0))
        self.assertFalse(redis_limiter.allow("t3", 1, now=204.0))

    def test_readyz_returns_503_on_oserror_or_sqlalchemy_error(self):
        for exc in (OSError("socket unreachable"), SQLAlchemyError("db error")):
            with patch("app.main.check_database", side_effect=exc):
                with self.assertRaises(HTTPException) as ctx:
                    readyz()
                self.assertEqual(ctx.exception.status_code, 503)
