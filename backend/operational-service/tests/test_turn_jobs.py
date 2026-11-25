from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import multiprocessing
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from app.schemas.ingest import ConsentIn
from app.schemas.whatsapp_turn import ProviderReceiptIn, TurnClaimIn, TurnCompleteIn, TurnEnqueueIn, TurnPrepareIn
from app.services.conversation_service import list_messages, list_pending_replies
from app.services.ingest_service import TURN_JOB_ATTEMPT_LIMIT, save_consent
from app.services.tenant_data import tenant_exec_options
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.whatsapp_turn_service import (
    begin_turn_send, claim_next_turn, claim_turn, complete_turn, enqueue_turn, prepare_turn, read_turn,
    record_provider_receipts, release_turn, retry_turn_job,
)
from app.tenant_models.operations import Message, MensajeProcesado
from app.tenant_models.whatsapp_consent import WhatsAppConsentState
from app.tenant_models.whatsapp_turn import WhatsAppSendEvidence, WhatsAppTurn, WhatsAppTurnJob
from test_message_identity import PostgresCase


def prepare_in_worker(database_url, tenant, account_key, committed, finish):
    engine = create_engine(database_url)
    with Session(engine) as db:
        claim = claim_next_turn(db, tenant, account_key)["job"]
        prepare_turn(db, tenant, claim["turn_id"], TurnPrepareIn(
            claim_token=claim["claim_token"], reply_body="Respuesta previa a la caída"))
    engine.dispose()
    committed.set()
    finish.wait(30)


class TurnJobTests(PostgresCase):
    account = "a" * 64
    other_account = "b" * 64
    phone = "12025550138"
    second_phone = "12025550139"

    def call(self, function, tenant, *args):
        with Session(self.engine) as db:
            return function(db, tenant, *args)

    def ready(self):
        tenant = self.tenant()
        for phone in (self.phone, self.second_phone):
            self.call(save_consent, tenant, ConsentIn(phone=phone, accepted=True))
        return tenant

    def job(self, external_message_id="queued-1", phone=phone, account_key=account):
        payload = self.payload(external_message_id=external_message_id, phone=phone).model_dump()
        return TurnEnqueueIn(**payload, recipient_jid=f"{phone}@s.whatsapp.net", account_key=account_key)

    def claim_next(self, tenant, account=None):
        return self.call(claim_next_turn, tenant, account or self.account)["job"]

    def expire(self, tenant, turn_id):
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.get(WhatsAppTurn, turn_id).lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

    def test_admission_is_idempotent_at_capacity_and_accepts_again_after_withdrawal(self):
        tenant = self.ready()
        with patch("app.services.ingest_service.TURN_JOB_CAPACITY", 1):
            first = self.call(enqueue_turn, tenant, self.job())
            self.assertEqual(first["disposition"], "accepted")
            repeated = self.call(enqueue_turn, tenant, self.job())
            self.assertEqual(repeated, first | {"disposition": "duplicate"})
            with self.assertRaises(HTTPException) as rejected:
                self.call(enqueue_turn, tenant, self.job("queued-2", self.second_phone))
            self.assertEqual(rejected.exception.status_code, 429)
            self.call(save_consent, tenant, ConsentIn(phone=self.phone, accepted=False))
            self.assertIsNone(self.claim_next(tenant))
            self.assertEqual(
                self.call(enqueue_turn, tenant, self.job("queued-2", self.second_phone))["disposition"], "accepted")
        self.assertEqual(self.call(read_turn, tenant, first["turn_id"])["state"], "cancelled")

    def test_failed_admission_rolls_back_the_message_turn_and_idempotency_marker(self):
        tenant = self.ready()
        with patch("app.services.ingest_service.create_system_event", side_effect=RuntimeError("Injected failure")):
            with self.assertRaises(RuntimeError):
                self.call(enqueue_turn, tenant, self.job())
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            for table in (Message, MensajeProcesado, WhatsAppTurn, WhatsAppTurnJob):
                self.assertEqual(db.scalar(select(func.count()).select_from(table)), 0)
        self.assertEqual(self.call(enqueue_turn, tenant, self.job())["disposition"], "accepted")

    def test_recovery_orders_each_contact_and_skips_another_workers_claim(self):
        tenant = self.ready()
        jobs = [self.job(), self.job("same-contact"), self.job("other-contact", self.second_phone)]
        identifiers = [self.call(enqueue_turn, tenant, job)["turn_id"] for job in jobs]
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: self.claim_next(tenant), range(8)))
        by_id = {job["turn_id"]: job for job in claims if job}
        self.assertEqual(sum(job is not None for job in claims), 2)
        self.assertEqual(set(by_id), {identifiers[0], identifiers[2]})
        first = by_id[identifiers[0]]
        self.expire(tenant, first["turn_id"])
        recovered = self.claim_next(tenant)
        self.assertEqual(recovered["turn_id"], first["turn_id"])
        self.assertNotEqual(recovered["claim_token"], first["claim_token"])
        with self.assertRaises(HTTPException):
            self.call(prepare_turn, tenant, first["turn_id"], TurnPrepareIn(
                claim_token=first["claim_token"], reply_body="Stale owner"))

    def test_queue_is_bound_to_account_and_tenant_and_legacy_claim_cannot_bypass_it(self):
        tenant, other = self.ready(), self.ready()
        first = self.call(enqueue_turn, tenant, self.job())
        self.assertIsNone(self.claim_next(tenant, self.other_account))
        self.assertIsNone(self.claim_next(other))
        with self.assertRaises(HTTPException) as rejected:
            self.call(enqueue_turn, tenant, self.job(account_key=self.other_account))
        self.assertEqual(rejected.exception.status_code, 409)
        legacy = TurnClaimIn(**self.job().model_dump())
        self.assertFalse(self.call(claim_turn, tenant, legacy)["claimed"])
        self.assertEqual(self.claim_next(tenant)["turn_id"], first["turn_id"])

    def test_failed_attempts_back_off_and_eventually_release_capacity(self):
        tenant = self.ready()
        first = self.call(enqueue_turn, tenant, self.job())
        for attempt in range(1, TURN_JOB_ATTEMPT_LIMIT + 1):
            claimed = self.claim_next(tenant)
            result = self.call(release_turn, tenant, first["turn_id"], claimed["claim_token"])
            self.assertIsNone(self.claim_next(tenant))
            with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
                job = db.get(WhatsAppTurnJob, first["turn_id"])
                self.assertEqual(job.attempts, attempt)
                self.assertGreater(job.available_at, datetime.now(timezone.utc))
                job.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
        self.assertEqual(result["last_error"], "attempt_limit_reached")
        self.assertIsNone(self.claim_next(tenant))
        with patch("app.services.ingest_service.TURN_JOB_CAPACITY", 1):
            self.assertEqual(self.call(enqueue_turn, tenant, self.job("queued-2"))["disposition"], "accepted")
            with self.assertRaises(HTTPException) as busy:
                self.call(retry_turn_job, tenant, first["turn_id"], self.account)
            self.assertEqual(busy.exception.status_code, 429)
        later = self.claim_next(tenant)
        with self.assertRaises(HTTPException):
            self.call(retry_turn_job, tenant, first["turn_id"], self.other_account)
        requeued = self.call(retry_turn_job, tenant, first["turn_id"], self.account)
        self.assertIsNone(requeued["claim_token"])
        self.assertIsNone(self.claim_next(tenant))
        self.expire(tenant, later["turn_id"])
        self.assertEqual(self.claim_next(tenant)["turn_id"], first["turn_id"])

    def test_late_withdrawal_protects_prior_jobs_without_overturning_later_grant(self):
        tenant = self.tenant()
        start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=2)
        first_accept = ConsentIn(phone=self.phone, accepted=True, external_message_id="consent-1", sent_at=start)
        self.call(save_consent, tenant, first_accept)
        old_job = self.job("from-prior-period").model_copy(update={"sent_at": start + timedelta(seconds=15)})
        queued = self.call(enqueue_turn, tenant, old_job)
        renewal = first_accept.model_copy(update={
            "external_message_id": "consent-2", "sent_at": start + timedelta(seconds=20),
        })
        self.call(save_consent, tenant, renewal)
        current_job = self.job("under-current-consent").model_copy(update={"sent_at": start + timedelta(seconds=21)})
        current = self.call(enqueue_turn, tenant, current_job)
        late_withdrawal = ConsentIn(phone=self.phone, accepted=False, external_message_id="late-withdrawal",
                                    sent_at=start + timedelta(seconds=10))
        result = self.call(save_consent, tenant, late_withdrawal)
        self.assertTrue(result["stale"])
        self.assertTrue(result["consentimiento_datos"])
        self.assertTrue(self.call(save_consent, tenant, late_withdrawal)["duplicate"])
        prior = self.call(read_turn, tenant, queued["turn_id"])
        self.assertEqual(prior["state"], "cancelled")
        self.assertEqual(prior["last_error"], "consent_superseded_by_renewal")
        self.assertEqual(self.claim_next(tenant)["turn_id"], current["turn_id"])
        with self.assertRaises(HTTPException) as rejected:
            self.call(enqueue_turn, tenant, old_job.model_copy(update={"external_message_id": "late-prior-input"}))
        self.assertEqual(rejected.exception.status_code, 403)

    def test_withdrawal_wins_same_second_in_both_delivery_orders(self):
        occurred = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(seconds=20)
        accept = ConsentIn(phone=self.phone, accepted=True, external_message_id="yes", sent_at=occurred)
        withdraw = ConsentIn(phone=self.phone, accepted=False, external_message_id="no", sent_at=occurred)
        for first, second in ((accept, withdraw), (withdraw, accept)):
            with self.subTest(first=first.accepted):
                tenant = self.tenant()
                self.call(save_consent, tenant, first)
                result = self.call(save_consent, tenant, second)
                self.assertFalse(result["consentimiento_datos"])
                older_accept = accept.model_copy(update={"external_message_id": "old", "sent_at": occurred - timedelta(seconds=1)})
                self.assertTrue(self.call(save_consent, tenant, older_accept)["stale"])
                next_accept = accept.model_copy(update={"external_message_id": "new", "sent_at": occurred + timedelta(seconds=1)})
                self.assertTrue(self.call(save_consent, tenant, next_accept)["consentimiento_datos"])

    def test_repeated_migration_keeps_existing_withdrawal_boundary(self):
        tenant = self.tenant()
        with self.engine.begin() as connection:
            WhatsAppConsentState.__table__.drop(connection.execution_options(**tenant_exec_options(tenant.schema_name)))
        self.call(save_consent, tenant, ConsentIn(phone=self.phone, accepted=True))
        self.call(save_consent, tenant, ConsentIn(phone=self.phone, accepted=False))
        for _ in range(2):
            with Session(self.engine) as db:
                apply_tenant_schema(db, tenant.schema_name)
                db.commit()
        replay = ConsentIn(phone=self.phone, accepted=True, external_message_id="pre-migration",
                           sent_at=datetime.now(timezone.utc) - timedelta(minutes=10))
        result = self.call(save_consent, tenant, replay)
        self.assertTrue(result["stale"])
        self.assertFalse(result["consentimiento_datos"])

    def test_expired_sending_is_parked_without_granting_a_second_send(self):
        tenant = self.ready()
        self.call(enqueue_turn, tenant, self.job())
        claimed = self.claim_next(tenant)
        turn_id, token = claimed["turn_id"], claimed["claim_token"]
        self.call(prepare_turn, tenant, turn_id, TurnPrepareIn(claim_token=token, reply_body="Persisted"))
        self.call(begin_turn_send, tenant, turn_id, token)
        self.expire(tenant, turn_id)
        self.assertIsNone(self.claim_next(tenant))
        self.assertEqual(self.call(read_turn, tenant, turn_id)["state"], "unknown")
        with self.assertRaises(HTTPException):
            self.call(retry_turn_job, tenant, turn_id, self.account)

    def test_prepared_turn_survives_termination_of_the_worker_process(self):
        tenant = self.ready()
        first = self.call(enqueue_turn, tenant, self.job())
        context = multiprocessing.get_context("spawn")
        committed, finish = context.Event(), context.Event()
        worker = context.Process(
            target=prepare_in_worker,
            args=(self.engine.url, tenant, self.account, committed, finish),
        )
        worker.start()
        try:
            self.assertTrue(committed.wait(15), "Worker did not commit its prepared response")
            self.assertIsNone(self.claim_next(tenant))
            worker.terminate()
            worker.join(timeout=5)
            self.assertIsNotNone(worker.exitcode)
            self.expire(tenant, first["turn_id"])
            resumed = self.claim_next(tenant)
            self.assertEqual(resumed["turn_id"], first["turn_id"])
            self.assertEqual(resumed["state"], "prepared")
            self.assertEqual(resumed["reply_body"], "Respuesta previa a la caída")
        finally:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
            worker.close()

    def test_additive_upgrade_preserves_a_legacy_turn_and_handles_repeat(self):
        tenant = self.ready()
        with self.engine.begin() as connection:
            WhatsAppSendEvidence.__table__.drop(connection.execution_options(**tenant_exec_options(tenant.schema_name)))
            WhatsAppTurnJob.__table__.drop(connection.execution_options(**tenant_exec_options(tenant.schema_name)))
        legacy = self.call(claim_turn, tenant, TurnClaimIn(**self.job().model_dump()))
        self.assertTrue(legacy["claimed"])
        with self.assertRaises(HTTPException) as rejected:
            self.claim_next(tenant)
        self.assertEqual(rejected.exception.status_code, 503)
        with Session(self.engine) as db:
            apply_tenant_schema(db, tenant.schema_name)
            apply_tenant_schema(db, tenant.schema_name)
            db.commit()
        self.assertTrue(inspect(self.engine).has_table(WhatsAppTurnJob.__tablename__, schema=tenant.schema_name))
        self.assertTrue(inspect(self.engine).has_table(WhatsAppSendEvidence.__tablename__, schema=tenant.schema_name))
        self.assertIsNone(self.claim_next(tenant))
        self.assertEqual(self.call(read_turn, tenant, legacy["turn_id"])["state"], "generating")

    def reserved_send(self, tenant, provider_id="provider-outbound", recipient_jid="123@lid"):
        admitted = self.call(enqueue_turn, tenant, self.job().model_copy(update={"recipient_jid": recipient_jid}))
        claim = self.claim_next(tenant)
        turn_id, token = admitted["turn_id"], claim["claim_token"]
        self.call(prepare_turn, tenant, turn_id, TurnPrepareIn(claim_token=token, reply_body="Respuesta reservada"))
        self.call(begin_turn_send, tenant, turn_id, token, provider_id)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            conversation_id = db.get(WhatsAppTurn, turn_id).conversation_id
        return turn_id, token, conversation_id

    def receipt(self, status, **changes):
        return ProviderReceiptIn(**({
            "status": status, "account_key": self.account, "provider_message_id": "provider-outbound",
            "recipient_jids": [f"{self.phone}@s.whatsapp.net"],
        } | changes))

    def test_receipt_recovers_unknown_send_and_ignores_another_tenant_account_or_recipient(self):
        tenant = self.ready()
        turn_id, token, chat = self.reserved_send(tenant)
        self.assertEqual(self.call(list_pending_replies, tenant, chat), [{"inbound_message_id": turn_id, "status": "sending"}])
        self.call(release_turn, tenant, turn_id, token)
        self.assertEqual(self.call(list_pending_replies, tenant, chat), [{"inbound_message_id": turn_id, "status": "unknown"}])
        self.assertEqual(self.call(record_provider_receipts, self.ready(), [self.receipt("read")]), {"applied": 0})
        self.assertEqual(self.call(record_provider_receipts, tenant, [
            self.receipt("read", account_key=self.other_account),
            self.receipt("read", recipient_jids=["818@lid"]),
            self.receipt("read", provider_message_id="other-id"),
        ]), {"applied": 0})
        self.assertEqual(self.call(record_provider_receipts, tenant, [self.receipt("read")]), {"applied": 1})
        self.assertEqual(self.call(list_pending_replies, tenant, chat), [])
        self.assertEqual(self.call(record_provider_receipts, tenant, [
            self.receipt("delivered"), self.receipt("failed"), self.receipt("read"),
        ]), {"applied": 0})
        self.call(complete_turn, tenant, turn_id, TurnCompleteIn(
            claim_token=token, provider_message_id="provider-outbound", sent_at=datetime.now(timezone.utc)))
        messages, total = self.call(list_messages, tenant, chat, 25, 0)
        self.assertEqual(total, 2)
        outbound = next(message for message in messages if message["direction"] == "outbound")
        self.assertEqual(outbound["delivery_status"], "read")

    def test_failure_reason_is_stored_and_stronger_delivery_evidence_wins(self):
        tenant = self.ready()
        turn_id, token, chat = self.reserved_send(tenant)
        with self.assertRaises(HTTPException) as conflict:
            self.call(complete_turn, tenant, turn_id, TurnCompleteIn(
                claim_token=token, provider_message_id="different-id", sent_at=datetime.now(timezone.utc)))
        self.assertEqual(conflict.exception.status_code, 409)
        self.assertEqual(self.call(record_provider_receipts, tenant, [
            self.receipt("failed", failure_reason="account_restricted"),
        ]), {"applied": 1})
        messages, _ = self.call(list_messages, tenant, chat, 25, 0)
        outbound = next(message for message in messages if message["direction"] == "outbound")
        self.assertEqual(outbound["delivery_failure_reason"], "account_restricted")
        with ThreadPoolExecutor(max_workers=4) as pool:
            states = ["sent", "delivered", "read", "failed"] * 3
            list(pool.map(lambda status: self.call(record_provider_receipts, tenant, [self.receipt(status)]), states))
        messages, total = self.call(list_messages, tenant, chat, 25, 0)
        self.assertEqual(total, 2)
        outbound = next(message for message in messages if message["direction"] == "outbound")
        self.assertEqual(outbound["delivery_status"], "read")
        self.assertIsNone(outbound["delivery_failure_reason"])
