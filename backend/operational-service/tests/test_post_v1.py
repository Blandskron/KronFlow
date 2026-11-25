from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.post_v1_service import (
    cancel_appointment,
    confirm_appointment,
    create_webhook_subscription,
    enqueue_webhook_delivery,
    get_private_attachment,
    purge_expired_attachments,
    record_webhook_attempt,
    register_private_attachment,
    sign_webhook_payload,
    simulate_appointment_slot,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.operations import Cliente, Conversation
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 19, 0, tzinfo=timezone.utc)
SLOT_START = T0 + timedelta(hours=2)
SLOT_END = T0 + timedelta(hours=3)
VALID_SHA = "a" * 64


class PostV1CapabilitiesTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int) -> TenantContext:
        tenant = TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="free",
            status="active",
        )
        with Session(self.engine) as db:
            apply_tenant_schema(db, schema)
            db.commit()
        with Session(self.engine) as db:
            bind_tenant_session(db, schema)
            db.add_all([
                Cliente(id=1, rut=f"r-{auth_id}", nombre="Cliente Agenda"),
                Conversation(id=1, session_id="56955551", message={"channel": "whatsapp"}),
            ])
            db.commit()
        return tenant

    def test_fk11_webhook_ssrf_guard_signing_dedup_and_dead_letter(self):
        tenant = self._seed_tenant("tenant_fk11_wh", 1101)
        with Session(self.engine) as db:
            # SSRF guard rejects non-https, localhost, and private IPs.
            for bad_url in ("http://hooks.example.com/in", "https://localhost/hook", "https://127.0.0.1/hook", "https://10.0.0.5/hook"):
                with self.assertRaises(HTTPException) as ctx:
                    create_webhook_subscription(db, tenant, name="Bad", target_url=bad_url, event_types=["lead.captured"], now=T0)
                self.assertEqual(ctx.exception.status_code, 422)

            sub = create_webhook_subscription(
                db, tenant, name="CRM Hook", target_url="https://hooks.partner.example/flowkron",
                event_types=["lead.captured"], max_attempts=2, actor_user_id="admin-1", now=T0,
            )
            payload = {"lead_id": 1}
            d1 = enqueue_webhook_delivery(db, tenant, sub["id"], event_id="evt_1", event_type="lead.captured", payload=payload, now=T0)
            d2 = enqueue_webhook_delivery(db, tenant, sub["id"], event_id="evt_1", event_type="lead.captured", payload=payload, now=T0)
            self.assertFalse(d1["duplicate"])
            self.assertTrue(d2["duplicate"])
            self.assertEqual(d1["signature"], sign_webhook_payload(sub["signing_secret"], "evt_1", payload))

            # Bounded attempts: attempt 1 -> failed, attempt 2 -> dead_letter.
            a1 = record_webhook_attempt(db, tenant, d1["id"], http_status=503, error="unavailable", now=T0)
            a2 = record_webhook_attempt(db, tenant, d1["id"], http_status=503, error="unavailable", now=T0)
            self.assertEqual((a1["status"], a1["attempts"]), ("failed", 1))
            self.assertEqual((a2["status"], a2["attempts"]), ("dead_letter", 2))

    def test_fk13_private_attachments_bounds_resource_scope_and_retention(self):
        tenant = self._seed_tenant("tenant_fk13_att", 1102)
        with Session(self.engine) as db:
            # Reject disallowed content_type and oversized file (>10MB).
            with self.assertRaises(HTTPException) as ctx_ct:
                register_private_attachment(
                    db, tenant, resource_type="conversation", resource_id=1, filename="x.exe",
                    content_type="application/x-msdownload", size_bytes=100, sha256_hex=VALID_SHA, uploaded_by="op-1", now=T0,
                )
            self.assertEqual(ctx_ct.exception.status_code, 422)

            with self.assertRaises(HTTPException) as ctx_sz:
                register_private_attachment(
                    db, tenant, resource_type="conversation", resource_id=1, filename="big.pdf",
                    content_type="application/pdf", size_bytes=10_485_761, sha256_hex=VALID_SHA, uploaded_by="op-1", now=T0,
                )
            self.assertEqual(ctx_sz.exception.status_code, 422)

            att = register_private_attachment(
                db, tenant, resource_type="conversation", resource_id=1, filename="../../evil/quote.pdf",
                content_type="application/pdf", size_bytes=2048, sha256_hex=VALID_SHA, uploaded_by="op-1", retention_days=10, now=T0,
            )
            self.assertEqual(att["filename"], "quote.pdf")

            # Resource-scoped read succeeds for matching resource, fails 404 for another resource.
            loaded = get_private_attachment(db, tenant, att["id"], resource_type="conversation", resource_id=1, now=T0)
            self.assertEqual(loaded["id"], att["id"])
            with self.assertRaises(HTTPException) as ctx_other:
                get_private_attachment(db, tenant, att["id"], resource_type="contact", resource_id=1, now=T0)
            self.assertEqual(ctx_other.exception.status_code, 404)

            # Expired attachment cannot be read and is purged cleanly.
            after_exp = T0 + timedelta(days=11)
            with self.assertRaises(HTTPException) as ctx_exp:
                get_private_attachment(db, tenant, att["id"], resource_type="conversation", resource_id=1, now=after_exp)
            self.assertEqual(ctx_exp.exception.status_code, 404)
            self.assertEqual(purge_expired_attachments(db, tenant, now=after_exp), 1)

    def test_fk22_scheduling_simulate_and_concurrent_confirm_prevent_double_booking(self):
        tenant = self._seed_tenant("tenant_fk22_cal", 1103)
        with Session(self.engine) as db:
            sim = simulate_appointment_slot(db, tenant, resource_key="advisor:1", starts_at=SLOT_START, ends_at=SLOT_END)
            self.assertTrue(sim["available"])

        def book(key: str) -> str:
            with Session(self.engine) as db:
                try:
                    res = confirm_appointment(
                        db,
                        tenant,
                        resource_key="advisor:1",
                        client_id=1,
                        conversation_id=1,
                        title="Test Drive",
                        starts_at=SLOT_START,
                        ends_at=SLOT_END,
                        idempotency_key=key,
                        actor_user_id="op-1",
                        now=T0,
                    )
                    return f"booked:{res['id']}"
                except HTTPException as exc:
                    return f"conflict:{exc.status_code}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(book, ["slot-req-1", "slot-req-2"]))

        booked = [o for o in outcomes if o.startswith("booked:")]
        conflicts = [o for o in outcomes if o == "conflict:409"]
        self.assertEqual(len(booked), 1, outcomes)
        self.assertEqual(len(conflicts), 1, outcomes)

        booked_id = int(booked[0].split(":")[1])
        with Session(self.engine) as db:
            sim_busy = simulate_appointment_slot(db, tenant, resource_key="advisor:1", starts_at=SLOT_START, ends_at=SLOT_END)
            self.assertFalse(sim_busy["available"])
            cancel_appointment(db, tenant, booked_id, now=T0)
            sim_free = simulate_appointment_slot(db, tenant, resource_key="advisor:1", starts_at=SLOT_START, ends_at=SLOT_END)
            self.assertTrue(sim_free["available"])
