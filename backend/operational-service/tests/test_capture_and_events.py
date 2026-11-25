from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.capture_service import (
    authenticate_scoped_credential,
    backfill_contact_points,
    capture_lead,
    create_public_form,
    issue_scoped_credential,
    resolve_public_form,
    revoke_scoped_credential,
)
from app.services.consent_authorization_service import evaluate_persisted_consent
from app.services.domain_event_service import (
    ack_subscription_checkpoint,
    poll_subscription_events,
    replay_domain_events,
    upsert_subscription,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.contact_capture import ContactPoint, LeadCapture
from app.tenant_models.operations import Cliente, Lead
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 15, 0, tzinfo=timezone.utc)
T_EXP = T0 + timedelta(hours=1)
T_AFTER_EXP = T0 + timedelta(hours=2)


class CaptureCredentialsAndDomainEventsTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int, *, status: str = "active") -> TenantContext:
        tenant = TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="free",
            status=status,
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
                    status=status,
                )
            )
            db.commit()
        return tenant

    def test_fk28_backfill_quarantines_collisions_and_is_repeatable(self):
        tenant = self._seed_tenant("tenant_fk28_bf", 2801)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add_all([
                Cliente(id=1, rut="r1", nombre="Ana", email="ana@Example.COM", telefono="+56 9 1111 1111"),
                Cliente(id=2, rut="r2", nombre="Luis", email="dup@example.com", telefono="bad-phone"),
                Cliente(id=3, rut="r3", nombre="Marta", email="dup@example.com", telefono="+56 9 2222 2222"),
            ])
            db.commit()

            first = backfill_contact_points(db, tenant)
            # Ana email + Ana phone + Marta phone = 3 inserted; dup@example.com = 1 collision; bad-phone = 1 unresolved
            self.assertEqual(first, {"inserted": 3, "skipped_existing": 0, "collisions": 1, "unresolved": 1})

            second = backfill_contact_points(db, tenant)
            self.assertEqual(second, {"inserted": 0, "skipped_existing": 3, "collisions": 1, "unresolved": 1})

    def test_fk12_scoped_credentials_and_fk28_capture_conflict_and_consent(self):
        tenant_a = self._seed_tenant("tenant_fk12_a", 2802)
        tenant_b = self._seed_tenant("tenant_fk12_b", 2803)

        with Session(self.engine) as db:
            # Issue scoped credential for leads:create.
            cred = issue_scoped_credential(
                db, tenant_a, name="Landing Integration", scopes=["leads:create"], expires_at=T_EXP, created_by="admin-a", now=T0,
            )
            resolved_tenant, resolved_cred = authenticate_scoped_credential(
                db, cred["api_key"], required_scope="leads:create", now=T0,
            )
            self.assertEqual(resolved_tenant.auth_tenant_id, tenant_a.auth_tenant_id)

            # Expired credential rejected with 401.
            with self.assertRaises(HTTPException) as ctx_exp:
                authenticate_scoped_credential(db, cred["api_key"], required_scope="leads:create", now=T_AFTER_EXP)
            self.assertEqual(ctx_exp.exception.status_code, 401)

            # Capture lead idempotently via integration + verify marketing opt-in is off by default.
            cap1 = capture_lead(
                db,
                resolved_tenant,
                source_kind="integration",
                source_ref=resolved_cred.key_prefix,
                idempotency_key="lead-req-1",
                name="Carlos",
                email="carlos@Example.TEST",
                phone="+56 9 3333 3333",
                marketing_opt_in=False,
                now=T0,
            )
            cap2 = capture_lead(
                db,
                resolved_tenant,
                source_kind="integration",
                source_ref=resolved_cred.key_prefix,
                idempotency_key="lead-req-1",
                name="Carlos",
                email="carlos@Example.TEST",
                phone="+56 9 3333 3333",
                marketing_opt_in=False,
                now=T0,
            )
            self.assertFalse(cap1["duplicate"])
            self.assertTrue(cap2["duplicate"])
            self.assertEqual(cap1["capture_id"], cap2["capture_id"])

            # Reusing same key with different payload returns 409.
            with self.assertRaises(HTTPException) as ctx_409:
                capture_lead(
                    db,
                    resolved_tenant,
                    source_kind="integration",
                    source_ref=resolved_cred.key_prefix,
                    idempotency_key="lead-req-1",
                    name="Tampered",
                    email="carlos@Example.TEST",
                    now=T0,
                )
            self.assertEqual(ctx_409.exception.status_code, 409)

            # Verify marketing consent was NOT granted implicitly.
            bind_tenant_session(db, tenant_a.schema_name)
            carlos = db.scalar(select(Cliente).where(Cliente.email == "carlos@example.test"))
            self.assertIsNotNone(carlos)
            self.assertEqual(
                evaluate_persisted_consent(
                    db, tenant_a, client_id=carlos.id, channel="email", destination="carlos@example.test", purpose="marketing", now=T0,
                ),
                "consent_missing",
            )

            # Create second independent contact with another phone, then trigger a cross-contact conflict capture.
            capture_lead(
                db,
                tenant_a,
                source_kind="integration",
                source_ref=resolved_cred.key_prefix,
                idempotency_key="lead-req-2",
                name="Sofia",
                phone="+56 9 4444 4444",
                now=T0,
            )
            conflict_cap = capture_lead(
                db,
                tenant_a,
                source_kind="integration",
                source_ref=resolved_cred.key_prefix,
                idempotency_key="lead-req-conflict",
                name="Ambiguous",
                email="carlos@example.test",
                phone="+56 9 4444 4444",
                now=T0,
            )
            bind_tenant_session(db, tenant_a.schema_name)
            stored_conflict = db.get(LeadCapture, conflict_cap["capture_id"])
            self.assertEqual(stored_conflict.status, "conflict_review")
            self.assertIsNone(stored_conflict.lead_id)

            # Revoked credential rejected with 401.
            revoke_scoped_credential(db, tenant_a, cred["id"], now=T0)
            with self.assertRaises(HTTPException) as ctx_rev:
                authenticate_scoped_credential(db, cred["api_key"], required_scope="leads:create", now=T0)
            self.assertEqual(ctx_rev.exception.status_code, 401)

            # Public form returns generic 202 (no contact/capture IDs), respects honeypot, and records explicit opt-in.
            form = create_public_form(db, tenant_b, name="Contacto Web", created_by="admin-b")
            f_tenant, f_obj = resolve_public_form(db, form["form_token"])
            self.assertEqual(f_tenant.auth_tenant_id, tenant_b.auth_tenant_id)
            pub_res = capture_lead(
                db,
                f_tenant,
                source_kind="public_form",
                source_ref=str(f_obj.id),
                idempotency_key="pub-1",
                name="Elena",
                email="elena@example.test",
                marketing_opt_in=True,
                now=T0,
            )
            self.assertEqual(pub_res, {"status": "accepted", "capture_id": None, "duplicate": False})

            # Honeypot submission is silently accepted without creating a lead.
            capture_lead(
                db,
                f_tenant,
                source_kind="public_form",
                source_ref=str(f_obj.id),
                idempotency_key="pub-bot",
                name="Bot",
                email="bot@example.test",
                honeypot="http://spam.test",
                now=T0,
            )
            bind_tenant_session(db, tenant_b.schema_name)
            self.assertEqual(db.query(Lead).count(), 1)
            elena = db.scalar(select(Cliente).where(Cliente.email == "elena@example.test"))
            self.assertEqual(
                evaluate_persisted_consent(
                    db, tenant_b, client_id=elena.id, channel="email", destination="elena@example.test", purpose="marketing", now=T0,
                ),
                "eligible",
            )

    def test_fk10_domain_event_replay_subscriptions_and_monotonic_checkpoints(self):
        tenant_a = self._seed_tenant("tenant_fk10_a", 2804)
        tenant_b = self._seed_tenant("tenant_fk10_b", 2805)

        with Session(self.engine) as db:
            # Capture two leads in tenant A -> emits contact.created + lead.captured events.
            capture_lead(
                db, tenant_a, source_kind="integration", source_ref="src-a", idempotency_key="e1",
                name="Uno", email="uno@example.test", now=T0,
            )
            capture_lead(
                db, tenant_a, source_kind="integration", source_ref="src-a", idempotency_key="e2",
                name="Uno", email="uno@example.test", now=T0,
            )

            # Forward replay returns events in strict ID order.
            replayed = replay_domain_events(db, tenant_a, after_id=0, limit=10)
            self.assertEqual([e["event_type"] for e in replayed["items"]], ["contact.created", "lead.captured", "lead.captured"])

            # Tenant B has zero events (strict isolation).
            replayed_b = replay_domain_events(db, tenant_b, after_id=0, limit=10)
            self.assertEqual(replayed_b["items"], [])

            # Subscribe only to lead.captured, poll, ack checkpoint, and verify monotonicity.
            sub = upsert_subscription(db, tenant_a, subscriber_name="analytics-worker", event_types=["lead.captured"], now=T0)
            self.assertEqual(sub["last_event_id"], 0)

            polled1 = poll_subscription_events(db, tenant_a, subscriber_name="analytics-worker", limit=1)
            self.assertEqual(len(polled1["items"]), 1)
            self.assertTrue(polled1["has_more"])
            first_id = polled1["items"][0]["id"]

            acked = ack_subscription_checkpoint(db, tenant_a, subscriber_name="analytics-worker", through_event_id=first_id, now=T0)
            self.assertEqual(acked["last_event_id"], first_id)

            # Backward ack must NOT regress checkpoint.
            acked_back = ack_subscription_checkpoint(db, tenant_a, subscriber_name="analytics-worker", through_event_id=0, now=T0)
            self.assertEqual(acked_back["last_event_id"], first_id)

            polled2 = poll_subscription_events(db, tenant_a, subscriber_name="analytics-worker", limit=10)
            self.assertEqual(len(polled2["items"]), 1)
            self.assertGreater(polled2["items"][0]["id"], first_id)
