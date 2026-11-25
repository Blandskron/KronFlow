from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.action_outbox_service import (
    begin_outbox_execution,
    cancel_outbox_action,
    claim_next_outbox_jobs,
    complete_outbox_action,
    enqueue_outbox_action,
    fail_outbox_action,
    reconcile_unknown_outbox_action,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.operations import Cliente
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


class ActionOutboxTests(PostgresCase):
    def _tenant(self, schema: str, auth_id: int) -> TenantContext:
        with Session(self.engine) as db:
            apply_tenant_schema(db, schema)
            db.commit()
        return TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="free",
            status="active",
        )

    def test_transactional_enqueue_idempotency_and_payload_conflict(self):
        tenant = self._tenant("tenant_fk03_idem", 301)
        payload = {"contact_id": 1, "template": "welcome-v1"}

        # Rollback must drop both domain write and outbox job atomically.
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(rut="fk03-rollback", nombre="Rollback Test"))
            enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="key-rollback", payload=payload,
            )
            db.rollback()

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.query(Cliente).count(), 0)
            self.assertEqual(db.query(ActionOutboxJob).count(), 0)

            job1, dup1 = enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="key-1", payload=payload, commit=True,
            )
            job2, dup2 = enqueue_outbox_action(
                db, tenant, action_type="campaign.email.send", idempotency_key="key-1", payload=payload, commit=True,
            )
            self.assertFalse(dup1)
            self.assertTrue(dup2)
            self.assertEqual(job1.id, job2.id)

            with self.assertRaises(HTTPException) as ctx:
                enqueue_outbox_action(
                    db,
                    tenant,
                    action_type="campaign.email.send",
                    idempotency_key="key-1",
                    payload={"contact_id": 1, "template": "tampered"},
                    commit=True,
                )
            self.assertEqual(ctx.exception.status_code, 409)

    def test_concurrent_workers_claim_distinct_jobs_without_duplicates(self):
        tenant = self._tenant("tenant_fk03_conc", 302)
        with Session(self.engine) as db:
            for idx in range(4):
                enqueue_outbox_action(
                    db,
                    tenant,
                    action_type="crm.action",
                    idempotency_key=f"batch-{idx}",
                    payload={"idx": idx},
                    available_at=T0,
                )
            db.commit()

        def worker():
            with Session(self.engine) as db:
                jobs = claim_next_outbox_jobs(db, tenant, limit=2, lease_seconds=60, now=T0)
                return [job.id for job in jobs]

        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: worker(), range(2)))

        self.assertEqual(len(first) + len(second), 4)
        self.assertEqual(set(first) & set(second), set())

    def test_executing_lease_expiry_moves_to_unknown_and_requires_effect_verification(self):
        tenant = self._tenant("tenant_fk03_unknown", 303)
        with Session(self.engine) as db:
            job, _ = enqueue_outbox_action(
                db,
                tenant,
                action_type="campaign.email.send",
                idempotency_key="send-1",
                payload={"to": "user@example.test"},
                max_attempts=3,
                available_at=T0,
                commit=True,
            )
            claimed = claim_next_outbox_jobs(db, tenant, limit=1, lease_seconds=60, now=T0)
            self.assertEqual(len(claimed), 1)
            executing = begin_outbox_execution(db, tenant, job.id, claimed[0].claim_token, now=T0)
            self.assertEqual(executing.state, "executing")

            # Cancellation must not cancel an already executing job.
            _, cancelled = cancel_outbox_action(db, tenant, job.id, reason="operator_cancel", now=T0)
            self.assertFalse(cancelled)

            # After lease expires, next claim sweep transitions executing -> unknown and does NOT blind-retry.
            after_expiry = T0 + timedelta(seconds=61)
            reclaimed = claim_next_outbox_jobs(db, tenant, limit=5, lease_seconds=60, now=after_expiry)
            self.assertEqual(reclaimed, [])
            db.expire_all()
            bind_tenant_session(db, tenant.schema_name)
            reloaded = db.get(ActionOutboxJob, job.id)
            self.assertEqual(reloaded.state, "unknown")
            self.assertEqual(reloaded.last_error, "execution_outcome_unknown")

            # Reconcile as verified NOT applied -> returns to pending for controlled retry.
            requeued = reconcile_unknown_outbox_action(
                db, tenant, job.id, verified_applied=False, retry_delay_seconds=10, now=after_expiry,
            )
            self.assertEqual(requeued.state, "pending")

            # Re-claim after backoff, execute, fail during executing -> unknown, then verify applied -> completed.
            t2 = after_expiry + timedelta(seconds=15)
            claimed2 = claim_next_outbox_jobs(db, tenant, limit=1, lease_seconds=60, now=t2)
            self.assertEqual(len(claimed2), 1)
            self.assertEqual(claimed2[0].attempts, 2)
            begin_outbox_execution(db, tenant, job.id, claimed2[0].claim_token, now=t2)
            failed_exec = fail_outbox_action(
                db, tenant, job.id, claimed2[0].claim_token, error="provider_timeout", retryable=True, now=t2,
            )
            self.assertEqual(failed_exec.state, "unknown")

            completed = reconcile_unknown_outbox_action(
                db,
                tenant,
                job.id,
                verified_applied=True,
                effect_reference="provider-msg-99",
                effect_payload={"status": "accepted"},
                now=t2,
            )
            self.assertEqual(completed.state, "completed")
            self.assertEqual(completed.effect_reference, "provider-msg-99")

    def test_retry_before_execution_and_tenant_isolation(self):
        tenant_a = self._tenant("tenant_fk03_iso_a", 304)
        tenant_b = self._tenant("tenant_fk03_iso_b", 305)
        with Session(self.engine) as db:
            job_a, _ = enqueue_outbox_action(
                db, tenant_a, action_type="crm.sync", idempotency_key="same-key", payload={"n": 1}, available_at=T0, commit=True,
            )
            job_b, _ = enqueue_outbox_action(
                db, tenant_b, action_type="crm.sync", idempotency_key="same-key", payload={"n": 2}, available_at=T0, commit=True,
            )
            self.assertEqual(job_a.id, 1)
            self.assertEqual(job_b.id, 1)

            claimed_a = claim_next_outbox_jobs(db, tenant_a, limit=1, lease_seconds=60, now=T0)
            # Retryable failure BEFORE begin_outbox_execution safely re-queues to pending.
            retried = fail_outbox_action(
                db, tenant_a, job_a.id, claimed_a[0].claim_token, error="temp_db_busy", retryable=True, retry_delay_seconds=5, now=T0,
            )
            self.assertEqual(retried.state, "pending")

            # Tenant B job remains unaffected and completable.
            claimed_b = claim_next_outbox_jobs(db, tenant_b, limit=1, lease_seconds=60, now=T0)
            self.assertEqual(len(claimed_b), 1)
            done_b = complete_outbox_action(
                db, tenant_b, job_b.id, claimed_b[0].claim_token, effect_reference="ok-b", now=T0,
            )
            self.assertEqual(done_b.state, "completed")
