from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import asyncio
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from test_message_identity import PostgresCase
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from app.core.database import get_db
from app.core.config import Settings
from app.main import app
from app.schemas.ingest import ConsentIn
from app.schemas.whatsapp_turn import TurnClaimIn, TurnCompleteIn, TurnPrepareIn, TurnReceiptIn
from app.services.ingest_service import save_consent
from app.services.tenant_data import tenant_exec_options
from app.services.whatsapp_turn_service import begin_turn_send, claim_turn, complete_turn, prepare_turn, read_turn, reconcile_turn, release_turn
from app.tenant_models.operations import Lead, Message
from app.tenant_models.whatsapp_turn import WhatsAppTurn


class TurnRecoveryTests(PostgresCase):
    def http(self, method, path, payload=None, headers=None):
        # Exercise the real ASGI application without TestClient/httpx. This
        # avoids the pre-existing optional HTTP-client dependency mismatch.
        async def run():
            data = json.dumps(payload).encode() if payload is not None else b""
            delivered = False
            output = []

            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": data, "more_body": False}
                await asyncio.Future()

            async def send(message):
                output.append(message)

            scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
                     "method": method, "scheme": "http", "http_version": "1.1", "root_path": "",
                     "path": path, "raw_path": path.encode(), "query_string": b"",
                     "headers": [(b"content-type", b"application/json")] +
                                [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()],
                     "client": ("127.0.0.1", 1), "server": ("test", 80)}
            await asyncio.wait_for(app(scope, receive, send), timeout=10)
            start = next(item for item in output if item["type"] == "http.response.start")
            body = b"".join(item.get("body", b"") for item in output if item["type"] == "http.response.body")
            return start["status"], json.loads(body), dict(start["headers"])
        return asyncio.run(run())

    def ready(self):
        tenant = self.tenant()
        with Session(self.engine) as db:
            save_consent(db, tenant, ConsentIn(phone="12025550138", accepted=True))
        return tenant

    def call(self, function, tenant, *args):
        with Session(self.engine) as db:
            return function(db, tenant, *args)

    def claim(self, tenant, **changes):
        return self.call(claim_turn, tenant, TurnClaimIn(**self.payload(**changes).model_dump()))

    def prepared(self, tenant, **changes):
        claimed = self.claim(tenant, **changes)
        data = TurnPrepareIn(claim_token=claimed["claim_token"], reply_body="Respuesta persistida", requires_human=True)
        self.call(prepare_turn, tenant, claimed["turn_id"], data)
        return claimed, data

    def acknowledgement(self, token):
        return TurnCompleteIn(claim_token=token, provider_message_id="outgoing-provider",
                              sent_at=datetime.now(timezone.utc))

    def expire(self, tenant, turn_id):
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.get(WhatsAppTurn, turn_id).lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()

    def test_concurrent_claimants_and_retry_after_generation_failure(self):
        tenant = self.ready()
        with ThreadPoolExecutor(max_workers=6) as pool:
            claims = list(pool.map(lambda _: self.claim(tenant), range(12)))
        self.assertEqual(sum(turn["claimed"] for turn in claims), 1)
        first = next(turn for turn in claims if turn["claimed"])
        self.call(release_turn, tenant, first["turn_id"], first["claim_token"])
        resumed = self.claim(tenant, body="Changed replay body")
        self.assertTrue(resumed["claimed"])
        self.assertEqual(resumed["input_body"], "Consulta sintética")
        self.assertNotEqual(resumed["claim_token"], first["claim_token"])
        with self.assertRaises(HTTPException):
            self.call(prepare_turn, tenant, first["turn_id"], TurnPrepareIn(claim_token=first["claim_token"], reply_body="Stale"))

    def test_entry_and_turn_are_atomic_when_initial_persistence_fails(self):
        tenant = self.ready()
        with patch("app.services.ingest_service.create_system_event", side_effect=RuntimeError("Injected failure")):
            with self.assertRaises(RuntimeError):
                self.claim(tenant)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(WhatsAppTurn)), 0)
        self.assertTrue(self.claim(tenant)["claimed"])

    def test_saved_reply_and_handoff_survive_response_loss_without_duplicate_effect(self):
        tenant = self.ready()
        first, data = self.prepared(tenant)
        self.call(prepare_turn, tenant, first["turn_id"], data)  # response lost, repeated request
        self.call(release_turn, tenant, first["turn_id"], first["claim_token"])
        resumed = self.claim(tenant)
        self.assertEqual(resumed["state"], "prepared")
        self.assertEqual(resumed["reply_body"], data.reply_body)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(Lead.estado_seguimiento)), "requiere_humano")
            self.assertEqual(db.scalar(select(func.count()).select_from(SystemEvent).where(
                SystemEvent.schema_name == tenant.schema_name, SystemEvent.event_type == "whatsapp.turn.handoff")), 1)

    def test_expired_generation_is_reclaimable_and_stale_worker_cannot_prepare(self):
        tenant = self.ready()
        first = self.claim(tenant)
        self.expire(tenant, first["turn_id"])
        second = self.claim(tenant)
        self.assertTrue(second["claimed"])
        with self.assertRaises(HTTPException):
            self.call(prepare_turn, tenant, first["turn_id"], TurnPrepareIn(claim_token=first["claim_token"], reply_body="Old"))

    def test_begin_send_is_not_repeatable_and_crash_never_grants_another_send(self):
        tenant = self.ready()
        first, _ = self.prepared(tenant)
        permit = self.call(begin_turn_send, tenant, first["turn_id"], first["claim_token"])
        self.assertTrue(permit["claimed"])
        with self.assertRaises(HTTPException):
            self.call(begin_turn_send, tenant, first["turn_id"], first["claim_token"])
        self.expire(tenant, first["turn_id"])
        resumed = self.claim(tenant)
        self.assertEqual(resumed["state"], "unknown")
        self.assertFalse(resumed["claimed"])
        self.assertIsNone(resumed["claim_token"])
        # A late acknowledgement from the original sender may resolve uncertainty.
        result = self.call(complete_turn, tenant, first["turn_id"], self.acknowledgement(first["claim_token"]))
        self.assertEqual(result["state"], "completed")

    def test_send_error_becomes_unknown_and_is_observable(self):
        tenant = self.ready()
        first, _ = self.prepared(tenant)
        self.call(begin_turn_send, tenant, first["turn_id"], first["claim_token"])
        self.call(release_turn, tenant, first["turn_id"], first["claim_token"])
        result = self.call(read_turn, tenant, first["turn_id"])
        self.assertEqual(result["state"], "unknown")
        self.assertEqual(result["last_error"], "send_outcome_unknown")
        self.assertIsNone(result["claim_token"])

    def test_operator_can_reconcile_verified_send_after_connector_restart(self):
        tenant = self.ready()
        first, _ = self.prepared(tenant)
        self.call(begin_turn_send, tenant, first["turn_id"], first["claim_token"])
        receipt = TurnReceiptIn(provider_message_id="verified-provider-id", sent_at=datetime.now(timezone.utc))
        with self.assertRaises(HTTPException):
            self.call(reconcile_turn, tenant, first["turn_id"], receipt)  # active lease, original sender may still run
        self.expire(tenant, first["turn_id"])
        result = self.call(reconcile_turn, tenant, first["turn_id"], receipt)
        self.assertEqual(result["state"], "completed")
        repeated = self.call(reconcile_turn, tenant, first["turn_id"], receipt)
        self.assertEqual(result["outbound_message_id"], repeated["outbound_message_id"])
        with self.assertRaises(HTTPException):
            self.call(reconcile_turn, tenant, first["turn_id"], TurnReceiptIn(
                provider_message_id="different-receipt", sent_at=receipt.sent_at))

    def test_completion_failure_rolls_back_message_and_retries_without_resending(self):
        tenant = self.ready()
        first, _ = self.prepared(tenant)
        self.call(begin_turn_send, tenant, first["turn_id"], first["claim_token"])
        ack = self.acknowledgement(first["claim_token"])
        with patch("app.services.whatsapp_turn_service.create_system_event", side_effect=RuntimeError("Injected failure")):
            with self.assertRaises(RuntimeError):
                self.call(complete_turn, tenant, first["turn_id"], ack)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 1)
            self.assertEqual(db.get(WhatsAppTurn, first["turn_id"]).state, "sending")
        completed = self.call(complete_turn, tenant, first["turn_id"], ack)
        repeated = self.call(complete_turn, tenant, first["turn_id"], ack)
        self.assertEqual(completed["outbound_message_id"], repeated["outbound_message_id"])
        self.assertFalse(self.claim(tenant)["claimed"])
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Message)), 2)

    def test_handoff_and_preparation_roll_back_together(self):
        tenant = self.ready()
        first = self.claim(tenant)
        with patch("app.services.whatsapp_turn_service.create_system_event", side_effect=RuntimeError("Injected failure")):
            with self.assertRaises(RuntimeError):
                self.call(prepare_turn, tenant, first["turn_id"], TurnPrepareIn(
                    claim_token=first["claim_token"], reply_body="Reply", requires_human=True))
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            self.assertIsNone(db.get(WhatsAppTurn, first["turn_id"]).reply_body)
            self.assertNotEqual(db.scalar(select(Lead.estado_seguimiento)), "requiere_humano")

    def test_withdrawal_before_send_cancels_without_releasing_a_send_permit(self):
        tenant = self.ready()
        first, _ = self.prepared(tenant)
        self.call(save_consent, tenant, ConsentIn(phone="12025550138", accepted=False))
        result = self.call(begin_turn_send, tenant, first["turn_id"], first["claim_token"])
        self.assertEqual(result["state"], "cancelled")
        self.assertFalse(result["claimed"])

    def test_untracked_legacy_messages_are_never_automatically_sent(self):
        tenant = self.ready()
        self.ingest(tenant, self.payload())
        result = self.claim(tenant)
        self.assertEqual(result["state"], "legacy_untracked")
        self.assertFalse(result.get("claimed", False))

    def test_turn_access_and_tokens_are_tenant_scoped(self):
        first_tenant, second_tenant = self.ready(), self.ready()
        first, second = self.claim(first_tenant), self.claim(second_tenant)
        with self.assertRaises(HTTPException):
            self.call(prepare_turn, second_tenant, first["turn_id"], TurnPrepareIn(
                claim_token=first["claim_token"], reply_body="Other tenant"))
        self.assertIsNone(self.call(read_turn, second_tenant, second["turn_id"])["claim_token"])

    def test_http_routes_enforce_credentials_validate_payloads_and_wrap_results(self):
        tenant = self.ready()
        with Session(self.engine) as db:
            db.add(TenantRuntime(auth_tenant_id=101, schema_name=tenant.schema_name, tenant_slug=tenant.tenant_slug,
                                 tenant_code=tenant.tenant_code, ingest_key_hash="unused", status="active", plan="free"))
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = sessions
        self.addCleanup(app.dependency_overrides.clear)
        path = "/api/v1/ingest/whatsapp/turns/claim"
        message = self.payload().model_dump(mode="json")
        status, rejected, _ = self.http("POST", path, message, {
            "X-Flowkron-Tenant": "101", "X-Baileys-Token": "untrusted"})
        self.assertEqual(status, 401)
        self.assertIsNone(rejected["meta"]["tenant_id"])
        headers = {"X-Flowkron-Tenant": "101", "X-Baileys-Token": "synthetic-turn-tests"}
        settings = Settings(_env_file=None, baileys_internal_token="synthetic-turn-tests")
        with patch("app.core.tenant_resolver.get_settings", return_value=settings):
            self.assertEqual(self.http("POST", path, message | {"direction": "outbound"}, headers)[0], 422)
            status, result, response_headers = self.http("POST", path, message, headers)
            self.assertEqual(status, 200)
            self.assertTrue(result["data"]["claimed"])
            self.assertEqual(result["meta"]["tenant_id"], "101")
            self.assertEqual(response_headers[b"cache-control"], b"no-store")
            turn = result["data"]
            turn_path = f"/api/v1/ingest/whatsapp/turns/{turn['turn_id']}"
            data = {"claim_token": turn["claim_token"], "reply_body": "Respuesta HTTP"}
            status, rejected, _ = self.http("POST", turn_path + "/prepare", data | {
                "claim_token": "synthetic-stale-claim-token"}, headers)
            self.assertEqual(status, 409)
            self.assertEqual(rejected["meta"]["tenant_id"], "101")
            self.assertEqual(self.http("POST", turn_path + "/prepare", data, headers)[0], 200)
            self.assertEqual(self.http("POST", turn_path + "/begin-send", {"claim_token": turn["claim_token"]}, headers)[0], 200)
            ack = self.acknowledgement(turn["claim_token"]).model_dump(mode="json")
            self.assertEqual(self.http("POST", turn_path + "/complete", ack, headers)[0], 200)
            _, result, _ = self.http("GET", turn_path, headers=headers)
            self.assertEqual(result["data"]["state"], "completed")
            self.assertIsNone(result["data"]["claim_token"])
