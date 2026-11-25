from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.campaign_service import (
    approve_campaign,
    create_campaign,
    create_template_with_version,
    ingest_channel_receipt,
    process_campaign_stub_batch,
    record_public_unsubscribe,
    render_template_preview,
    set_campaign_state,
)
from app.services.channel_connection_service import (
    create_channel_connection,
    revoke_channel_connection,
    rotate_channel_connection,
    send_conversation_email,
)
from app.services.consent_authorization_service import evaluate_persisted_consent, record_consent_decision
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.campaigns import CampaignRecipient, TemplateVersion
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.operations import Cliente, Conversation, Message
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 16, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=5)
T2 = T0 + timedelta(minutes=10)


class CampaignsAndChannelsTests(PostgresCase):
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
            db.add(
                TenantRuntime(
                    auth_tenant_id=auth_id,
                    tenant_slug=schema,
                    schema_name=schema,
                    tenant_code=schema,
                    ingest_key_hash="unused",
                    plan="free",
                    status="active",
                )
            )
            db.commit()
        return tenant

    def test_fk30_template_sanitization_and_html_escape_preview(self):
        tenant = self._seed_tenant("tenant_fk30_tmpl", 3001)
        with Session(self.engine) as db:
            # Disallowed <script> rejected.
            with self.assertRaises(HTTPException) as ctx_xss:
                create_template_with_version(
                    db, tenant, name="Bad", channel="email", subject="Hi", body_text="Hello",
                    body_html="<p>Hi</p><script>alert(1)</script>", actor_user_id="u1", now=T0,
                )
            self.assertEqual(ctx_xss.exception.status_code, 422)

            # Undeclared variable rejected.
            with self.assertRaises(HTTPException) as ctx_var:
                create_template_with_version(
                    db, tenant, name="BadVar", channel="email", subject="Hi {{name}}", body_text="Hello",
                    declared_variables=[], actor_user_id="u1", now=T0,
                )
            self.assertEqual(ctx_var.exception.status_code, 422)

            created = create_template_with_version(
                db, tenant, name="Promo", channel="email", subject="Hola {{name}}",
                body_text="Hola {{name}}", body_html="<p>Hola {{name}}</p>",
                declared_variables=["name"], approve_immediately=True, actor_user_id="u1", now=T0,
            )
            bind_tenant_session(db, tenant.schema_name)
            tv = db.get(TemplateVersion, created["template_version_id"])
            preview = render_template_preview(tv, {"name": "<script>x</script>"})
            self.assertEqual(preview["body_html"], "<p>Hola &lt;script&gt;x&lt;/script&gt;</p>")

    def test_fk30_campaign_snapshot_concurrent_unsubscribe_stub_dispatch_and_receipts(self):
        tenant = self._seed_tenant("tenant_fk30_e2e", 3002)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add_all([
                Cliente(id=1, rut="r1", nombre="Uno", email="uno@example.test"),
                Cliente(id=2, rut="r2", nombre="Dos", email="dos@example.test"),
                Cliente(id=3, rut="r3", nombre="Tres", email="tres@example.test"),
            ])
            db.flush()
            db.add_all([
                ContactPoint(id=1, client_id=1, point_type="email", normalized_value="uno@example.test", status="active", verified=True),
                ContactPoint(id=2, client_id=2, point_type="email", normalized_value="dos@example.test", status="active", verified=True),
                ContactPoint(id=3, client_id=3, point_type="email", normalized_value="tres@example.test", status="active", verified=True),
            ])
            db.commit()

            # Grant marketing consent to Uno and Dos (Tres has no consent).
            for cid, addr in ((1, "uno@example.test"), (2, "dos@example.test")):
                record_consent_decision(
                    db, tenant, client_id=cid, channel="email", destination=addr, purpose="marketing",
                    granted=True, effective_at=T0, recorded_at=T0, source="form",
                )

            conn = create_channel_connection(
                db, tenant, channel="email", provider="stub", sender_address="news@acme.test",
                display_name="Acme News", verified=True, sandbox_only=True, actor_user_id="admin-1", now=T0,
            )
            tmpl = create_template_with_version(
                db, tenant, name="Launch", channel="email", subject="Novedades",
                body_text="Hola desde Flowkron", approve_immediately=True, actor_user_id="admin-1", now=T0,
            )
            camp = create_campaign(
                db, tenant, name="Campaña Noviembre", channel="email", purpose="marketing",
                template_version_id=tmpl["template_version_id"], connection_id=conn["id"],
                timezone_iana="America/Santiago", actor_user_id="admin-1", now=T0,
            )

            # Approve -> snapshot contains ONLY Uno and Dos (2 queued).
            approved = approve_campaign(db, tenant, camp["id"], expected_version=1, actor_user_id="admin-1", now=T0)
            self.assertEqual(approved["status"], "running")
            self.assertEqual(approved["recipient_counts"], {"queued": 2})

            # Dos unsubscribes AFTER approval and BEFORE dispatch!
            unsub = record_public_unsubscribe(db, tenant, channel="email", destination="dos@example.test", purpose="marketing", now=T1)
            self.assertEqual(unsub, {"status": "unsubscribed"})

            # Stub worker dispatches: Uno accepted, Dos suppressed!
            dispatch = process_campaign_stub_batch(db, tenant, limit=10, now=T1)
            self.assertEqual((dispatch["claimed"], dispatch["accepted"], dispatch["suppressed"]), (2, 1, 1))

            bind_tenant_session(db, tenant.schema_name)
            rec_uno = db.scalar(select(CampaignRecipient).where(CampaignRecipient.destination == "uno@example.test"))
            rec_dos = db.scalar(select(CampaignRecipient).where(CampaignRecipient.destination == "dos@example.test"))
            self.assertEqual(rec_uno.status, "accepted")
            self.assertEqual(rec_dos.status, "suppressed")

            # Ingest receipts: delivered -> duplicate delivered -> bounced (creates durable suppression!).
            r1 = ingest_channel_receipt(
                db, tenant, provider_account_id="stub-acct", provider_event_id="ev-1",
                event_type="delivered", provider_message_id=rec_uno.provider_message_id, occurred_at=T2,
            )
            r1_dup = ingest_channel_receipt(
                db, tenant, provider_account_id="stub-acct", provider_event_id="ev-1",
                event_type="delivered", provider_message_id=rec_uno.provider_message_id, occurred_at=T2,
            )
            self.assertFalse(r1["duplicate"])
            self.assertTrue(r1_dup["duplicate"])

            ingest_channel_receipt(
                db, tenant, provider_account_id="stub-acct", provider_event_id="ev-2",
                event_type="bounced", provider_message_id=rec_uno.provider_message_id, occurred_at=T2,
            )
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.get(CampaignRecipient, rec_uno.id).status, "bounced")
            self.assertEqual(
                evaluate_persisted_consent(
                    db, tenant, client_id=1, channel="email", destination="uno@example.test", purpose="marketing", now=T2,
                ),
                "suppressed",
            )

            # Pause and cancel with optimistic version.
            paused = set_campaign_state(db, tenant, camp["id"], action="pause", expected_version=2, now=T2)
            self.assertEqual((paused["status"], paused["version"]), ("paused", 3))
            cancelled = set_campaign_state(db, tenant, camp["id"], action="cancel", expected_version=3, now=T2)
            self.assertEqual((cancelled["status"], cancelled["version"]), ("cancelled", 4))

    def test_fk24_connection_rotation_revocation_and_fk23_conversation_email(self):
        tenant = self._seed_tenant("tenant_fk24_23", 3003)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Conversation(id=1, session_id="56912345678", message={"channel": "whatsapp"}))
            db.commit()

            conn = create_channel_connection(
                db, tenant, channel="email", provider="resend", sender_address="soporte@acme.test",
                display_name="Soporte Acme", verified=True, sandbox_only=True, provider_secret="re_initial",
                actor_user_id="admin-1", now=T0,
            )
            rotated = rotate_channel_connection(
                db, tenant, conn["id"], new_provider_secret="re_rotated", actor_user_id="admin-1", now=T1,
            )
            self.assertEqual(rotated["credential_version"], 2)

            # FK-23: Send conversation-linked email idempotently.
            sent1 = send_conversation_email(
                db, tenant, 1, connection_id=conn["id"], to_email="cliente@example.test",
                subject="Resumen de solicitud", body_text="Adjuntamos detalle.", idempotency_key="em-1",
                actor_user_id="op-1", now=T1,
            )
            sent2 = send_conversation_email(
                db, tenant, 1, connection_id=conn["id"], to_email="cliente@example.test",
                subject="Resumen de solicitud", body_text="Adjuntamos detalle.", idempotency_key="em-1",
                actor_user_id="op-1", now=T1,
            )
            self.assertFalse(sent1["duplicate"])
            self.assertTrue(sent2["duplicate"])
            self.assertEqual(sent1["message_id"], sent2["message_id"])

            bind_tenant_session(db, tenant.schema_name)
            msg = db.get(Message, sent1["message_id"])
            self.assertEqual((msg.channel, msg.direction), ("email", "outbound"))

            # Revoking connection blocks subsequent conversation emails (409).
            revoked = revoke_channel_connection(db, tenant, conn["id"], actor_user_id="admin-1", now=T2)
            self.assertEqual(revoked["status"], "revoked")
            with self.assertRaises(HTTPException) as ctx_rev:
                send_conversation_email(
                    db, tenant, 1, connection_id=conn["id"], to_email="cliente@example.test",
                    subject="Otro", body_text="Bloqueado", idempotency_key="em-2", actor_user_id="op-1", now=T2,
                )
            self.assertEqual(ctx_rev.exception.status_code, 409)

            # WhatsApp non-stub campaign provider remains gated (422).
            wa_conn = create_channel_connection(
                db, tenant, channel="whatsapp", provider="whatsapp_business_official", sender_address="+56900000000",
                display_name="WA Official", verified=True, sandbox_only=True, actor_user_id="admin-1", now=T2,
            )
            wa_tmpl = create_template_with_version(
                db, tenant, name="WA", channel="whatsapp", body_text="Hola", approve_immediately=True, actor_user_id="admin-1", now=T2,
            )
            with self.assertRaises(HTTPException) as ctx_wa:
                create_campaign(
                    db, tenant, name="WA Real", channel="whatsapp", purpose="marketing",
                    template_version_id=wa_tmpl["template_version_id"], connection_id=wa_conn["id"],
                    actor_user_id="admin-1", now=T2,
                )
            self.assertEqual(ctx_wa.exception.status_code, 422)
