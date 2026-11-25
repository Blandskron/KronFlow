from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.action_outbox_service import claim_next_outbox_jobs, enqueue_outbox_action
from app.services.consent_authorization_service import (
    authorize_outbox_delivery,
    evaluate_persisted_consent,
    record_consent_decision,
    record_suppression,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.operations import Cliente
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 10, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(minutes=10)
T2 = T0 + timedelta(minutes=20)


class ConsentAuthorizationTests(PostgresCase):
    def _seed_tenant_with_contact(self, schema: str, auth_id: int, status: str = "active") -> tuple[TenantContext, int]:
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
        with Session(self.engine) as db:
            bind_tenant_session(db, schema)
            contact = Cliente(id=1, rut=f"rut-{auth_id}", nombre=f"Contact {auth_id}", email="lead@example.test")
            db.add(contact)
            db.commit()
        return tenant, 1

    def test_persisted_consent_and_transactional_worker_authorization(self):
        tenant, client_id = self._seed_tenant_with_contact("tenant_fk04_auth", 401)
        dest = "lead@example.test"

        with Session(self.engine) as db:
            # Without explicit consent, worker authorization cancels the job with consent_missing.
            job_missing, _ = enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="m1", payload={"to": dest}, available_at=T0, commit=True,
            )
            claimed = claim_next_outbox_jobs(db, tenant, limit=1, lease_seconds=60, now=T0)
            res = authorize_outbox_delivery(
                db,
                tenant,
                job_id=job_missing.id,
                claim_token=claimed[0].claim_token,
                client_id=client_id,
                channel="email",
                destination=dest,
                purpose="marketing",
                now=T0,
            )
            self.assertFalse(res.authorized)
            self.assertEqual(res.reason, "consent_missing")
            self.assertEqual(res.job_state, "cancelled")

            # Record opt-in for marketing -> worker authorizes and transitions job to executing.
            record_consent_decision(
                db,
                tenant,
                client_id=client_id,
                channel="email",
                destination=dest,
                purpose="marketing",
                granted=True,
                effective_at=T0,
                recorded_at=T0,
                source="form",
                policy_version="v1.0",
            )
            job_ok, _ = enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="m2", payload={"to": dest}, available_at=T1, commit=True,
            )
            claimed_ok = claim_next_outbox_jobs(db, tenant, limit=1, lease_seconds=60, now=T1)
            res_ok = authorize_outbox_delivery(
                db,
                tenant,
                job_id=job_ok.id,
                claim_token=claimed_ok[0].claim_token,
                client_id=client_id,
                channel="email",
                destination=dest,
                purpose="marketing",
                now=T1,
            )
            self.assertTrue(res_ok.authorized)
            self.assertEqual(res_ok.reason, "eligible")
            self.assertEqual(res_ok.job_state, "executing")

            # Suppression (unsubscribe) blocks subsequent jobs even with prior opt-in.
            record_suppression(
                db,
                tenant,
                client_id=client_id,
                channel="email",
                destination=dest,
                purpose="marketing",
                reason="unsubscribe",
                source="unsubscribe_link",
                recorded_at=T2,
            )
            job_sup, _ = enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="m3", payload={"to": dest}, available_at=T2, commit=True,
            )
            claimed_sup = claim_next_outbox_jobs(db, tenant, limit=1, lease_seconds=60, now=T2)
            res_sup = authorize_outbox_delivery(
                db,
                tenant,
                job_id=job_sup.id,
                claim_token=claimed_sup[0].claim_token,
                client_id=client_id,
                channel="email",
                destination=dest,
                purpose="marketing",
                now=T2,
            )
            self.assertFalse(res_sup.authorized)
            self.assertEqual(res_sup.reason, "suppressed")
            self.assertEqual(res_sup.job_state, "cancelled")

    def test_concurrent_suppression_and_authorization_serialize_cleanly(self):
        tenant, client_id = self._seed_tenant_with_contact("tenant_fk04_race", 402)
        dest = "lead@example.test"
        with Session(self.engine) as db:
            record_consent_decision(
                db,
                tenant,
                client_id=client_id,
                channel="email",
                destination=dest,
                purpose="marketing",
                granted=True,
                effective_at=T0,
                recorded_at=T0,
                source="operational",
            )
            job, _ = enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="race-1", payload={"to": dest}, available_at=T1, commit=True,
            )
            claimed = claim_next_outbox_jobs(db, tenant, limit=1, lease_seconds=60, now=T1)
            claim_token = claimed[0].claim_token

        def run_authorize():
            with Session(self.engine) as db:
                return authorize_outbox_delivery(
                    db,
                    tenant,
                    job_id=job.id,
                    claim_token=claim_token,
                    client_id=client_id,
                    channel="email",
                    destination=dest,
                    purpose="marketing",
                    now=T1,
                )

        def run_suppress():
            with Session(self.engine) as db:
                record_suppression(
                    db,
                    tenant,
                    client_id=client_id,
                    channel="email",
                    destination=dest,
                    purpose=None,
                    reason="baja",
                    source="whatsapp_message",
                    recorded_at=T1,
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            f_auth = pool.submit(run_authorize)
            f_sup = pool.submit(run_suppress)
            auth_result = f_auth.result()
            f_sup.result()

        # Either suppression won (cancelled/suppressed) or authorization won (executing/eligible),
        # and in both cases any subsequent evaluation is suppressed.
        self.assertIn((auth_result.authorized, auth_result.job_state), [(True, "executing"), (False, "cancelled")])
        with Session(self.engine) as db:
            self.assertEqual(
                evaluate_persisted_consent(
                    db, tenant, client_id=client_id, channel="email", destination=dest, purpose="marketing", now=T1,
                ),
                "suppressed",
            )

    def test_suspended_tenant_and_tenant_isolation(self):
        tenant_a, client_a = self._seed_tenant_with_contact("tenant_fk04_iso_a", 403, status="active")
        tenant_b, client_b = self._seed_tenant_with_contact("tenant_fk04_iso_b", 404, status="suspended")
        dest = "shared@example.test"

        with Session(self.engine) as db:
            # Grant only in tenant_a; tenant_b has identical client_id=1 and destination.
            record_consent_decision(
                db,
                tenant_a,
                client_id=client_a,
                channel="email",
                destination=dest,
                purpose="marketing",
                granted=True,
                effective_at=T0,
                recorded_at=T0,
                source="form",
            )
            self.assertEqual(
                evaluate_persisted_consent(
                    db, tenant_a, client_id=client_a, channel="email", destination=dest, purpose="marketing", now=T1,
                ),
                "eligible",
            )
            self.assertEqual(
                evaluate_persisted_consent(
                    db, tenant_b, client_id=client_b, channel="email", destination=dest, purpose="marketing", now=T1,
                ),
                "consent_missing",
            )

            # Even if tenant_b had opt-in, suspended runtime blocks worker send authorization.
            record_consent_decision(
                db,
                tenant_b,
                client_id=client_b,
                channel="email",
                destination=dest,
                purpose="marketing",
                granted=True,
                effective_at=T0,
                recorded_at=T0,
                source="form",
            )
            job_b, _ = enqueue_outbox_action(
                db, tenant_b, action_type="campaign.email.send", idempotency_key="susp-1", payload={"to": dest}, available_at=T1, commit=True,
            )
            claimed_b = claim_next_outbox_jobs(db, tenant_b, limit=1, lease_seconds=60, now=T1)
            res_b = authorize_outbox_delivery(
                db,
                tenant_b,
                job_id=job_b.id,
                claim_token=claimed_b[0].claim_token,
                client_id=client_b,
                channel="email",
                destination=dest,
                purpose="marketing",
                now=T1,
            )
            self.assertFalse(res_b.authorized)
            self.assertEqual(res_b.reason, "tenant_suspended")
            self.assertEqual(res_b.job_state, "cancelled")

            # Confirm persisted job state in tenant_b schema.
            bind_tenant_session(db, tenant_b.schema_name)
            row = db.scalar(select(ActionOutboxJob).where(ActionOutboxJob.id == job_b.id))
            self.assertEqual(row.state, "cancelled")
            self.assertEqual(row.last_error, "tenant_suspended")
