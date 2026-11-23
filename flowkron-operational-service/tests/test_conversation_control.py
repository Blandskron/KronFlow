from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.whatsapp_turn import TurnClaimIn
from app.services.conversation_control_service import (
    claim_conversation,
    get_conversation_control,
    request_handoff,
    resolve_conversation,
    return_conversation_to_ai,
    send_human_reply,
    set_tenant_ai_policy,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.whatsapp_turn_service import claim_turn
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.conversation_control import ConversationControlEvent
from app.tenant_models.operations import Cliente, Conversation, Lead, Message
from app.tenant_models.whatsapp_turn import WhatsAppTurn
from test_message_identity import PostgresCase


PHONE = "12025550199"
T0 = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


class ConversationControlTests(PostgresCase):
    def _seed_conversation(
        self, schema: str, auth_id: int, *, consent: bool = True, status: str = "active",
    ) -> tuple[TenantContext, int]:
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
            cliente = Cliente(
                id=1,
                rut=f"rut-{auth_id}",
                nombre=f"Contact {auth_id}",
                whatsapp_id=PHONE,
                consentimiento_datos=consent,
            )
            conv = Conversation(id=1, session_id=PHONE, message={"channel": "whatsapp"})
            db.add_all([cliente, conv])
            db.flush()
            db.add(Lead(id=1, cliente_id=1))
            db.commit()
        return tenant, 1

    def test_concurrent_claims_allow_only_one_active_operator(self):
        tenant, conv_id = self._seed_conversation("tenant_fk06_cas", 601)

        def try_claim(operator_id: str) -> str:
            with Session(self.engine) as db:
                try:
                    res = claim_conversation(
                        db, tenant, conv_id, actor_user_id=operator_id, expected_version=1, now=T0,
                    )
                    return f"won:{res['owner_user_id']}"
                except HTTPException as exc:
                    return f"conflict:{exc.status_code}"

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(try_claim, ["op-1", "op-2"]))

        winners = [o for o in outcomes if o.startswith("won:")]
        conflicts = [o for o in outcomes if o == "conflict:409"]
        self.assertEqual(len(winners), 1, outcomes)
        self.assertEqual(len(conflicts), 1, outcomes)

    def test_human_reply_ownership_idempotency_and_lifecycle(self):
        tenant, conv_id = self._seed_conversation("tenant_fk06_flow", 602)

        with Session(self.engine) as db:
            # Handoff: ai_active (v1) -> waiting_human (v2)
            ho = request_handoff(db, tenant, conv_id, actor_user_id="op-1", reason="vip_escalation", expected_version=1, now=T0)
            self.assertEqual((ho["mode"], ho["control_version"]), ("waiting_human", 2))

            # Claim: waiting_human (v2) -> human_active (v3) by op-1
            claimed = claim_conversation(db, tenant, conv_id, actor_user_id="op-1", expected_version=2, now=T0)
            self.assertEqual((claimed["mode"], claimed["owner_user_id"], claimed["control_version"]), ("human_active", "op-1", 3))

            # Another non-supervisor operator cannot send a reply (403).
            with self.assertRaises(HTTPException) as ctx:
                send_human_reply(db, tenant, conv_id, actor_user_id="op-2", body="Hola", idempotency_key="r1", now=T0)
            self.assertEqual(ctx.exception.status_code, 403)

            # Owner queues reply idempotently into outbox + message store.
            first = send_human_reply(db, tenant, conv_id, actor_user_id="op-1", body="Hola cliente", idempotency_key="r1", now=T0)
            second = send_human_reply(db, tenant, conv_id, actor_user_id="op-1", body="Hola cliente", idempotency_key="r1", now=T0)
            self.assertFalse(first["duplicate"])
            self.assertTrue(second["duplicate"])
            self.assertEqual(first["outbox_job_id"], second["outbox_job_id"])
            self.assertEqual(first["message_id"], second["message_id"])

            # Verify outbox row persisted.
            bind_tenant_session(db, tenant.schema_name)
            job = db.get(ActionOutboxJob, first["outbox_job_id"])
            self.assertEqual(job.action_type, "conversation.human_reply.send")
            self.assertEqual(job.state, "pending")

            # Return to AI: human_active (v3) -> ai_active (v4)
            returned = return_conversation_to_ai(db, tenant, conv_id, actor_user_id="op-1", expected_version=3, now=T0)
            self.assertEqual((returned["mode"], returned["owner_user_id"], returned["control_version"]), ("ai_active", None, 4))

            # Claim again (v4 -> v5) and resolve (v5 -> v6).
            claim_conversation(db, tenant, conv_id, actor_user_id="op-2", expected_version=4, now=T0)
            resolved = resolve_conversation(
                db, tenant, conv_id, actor_user_id="op-2", expected_version=5, reason="sale_closed", now=T0,
            )
            self.assertEqual((resolved["mode"], resolved["control_version"], resolved["resolution_reason"]), ("resolved", 6, "sale_closed"))

            # Audit trail has 5 transitions.
            bind_tenant_session(db, tenant.schema_name)
            events = db.scalars(select(ConversationControlEvent).order_by(ConversationControlEvent.id)).all()
            self.assertEqual([e.to_mode for e in events], ["waiting_human", "human_active", "ai_active", "human_active", "resolved"])

    def test_fk19_human_control_and_tenant_policy_block_ai_without_cancelling_sending(self):
        tenant, conv_id = self._seed_conversation("tenant_fk19_block", 603)

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            m1 = Message(id=10, whatsapp_id=PHONE, rol="usuario", direction="inbound", mensaje="hola 1", external_message_id="ext-10")
            m2 = Message(id=11, whatsapp_id=PHONE, rol="usuario", direction="inbound", mensaje="hola 2", external_message_id="ext-11")
            db.add_all([m1, m2])
            db.flush()
            # Turn 10 is recoverable (prepared); turn 11 is already sending (must NOT be cancelled).
            db.add_all([
                WhatsAppTurn(id=10, lead_id=1, conversation_id=conv_id, phone=PHONE, state="prepared", reply_body="draft"),
                WhatsAppTurn(id=11, lead_id=1, conversation_id=conv_id, phone=PHONE, state="sending", reply_body="in-flight"),
            ])
            db.commit()

            # Human claims conversation -> cancels turn 10, preserves turn 11.
            claimed = claim_conversation(db, tenant, conv_id, actor_user_id="op-1", expected_version=1, now=T0)
            self.assertEqual(claimed["cancelled_ai_turns"], 1)

            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.get(WhatsAppTurn, 10).state, "cancelled")
            self.assertEqual(db.get(WhatsAppTurn, 11).state, "sending")

            # New incoming AI turn must be cancelled immediately and NOT claimed.
            turn_res = claim_turn(
                db,
                tenant,
                TurnClaimIn(external_message_id="ext-12", phone=PHONE, body="nuevo mensaje", sent_at=T0),
            )
            self.assertFalse(turn_res["claimed"])
            self.assertEqual(turn_res["state"], "cancelled")
            self.assertEqual(turn_res["last_error"], "control_human_active")

            # Return to AI, then disable tenant-wide AI policy -> blocks new AI turns too.
            return_conversation_to_ai(db, tenant, conv_id, actor_user_id="op-1", expected_version=2, now=T0)
            policy = set_tenant_ai_policy(db, tenant, ai_enabled=False, actor_user_id="admin-1", reason="maintenance", now=T0)
            self.assertFalse(policy["ai_enabled"])

            turn_res2 = claim_turn(
                db,
                tenant,
                TurnClaimIn(external_message_id="ext-13", phone=PHONE, body="otro mensaje", sent_at=T0),
            )
            self.assertFalse(turn_res2["claimed"])
            self.assertEqual(turn_res2["state"], "cancelled")
            self.assertEqual(turn_res2["last_error"], "tenant_ai_disabled")

    def test_multi_tenant_control_isolation(self):
        tenant_a, conv_a = self._seed_conversation("tenant_fk06_iso_a", 604)
        tenant_b, conv_b = self._seed_conversation("tenant_fk06_iso_b", 605)
        self.assertEqual(conv_a, conv_b)

        with Session(self.engine) as db:
            claim_conversation(db, tenant_a, conv_a, actor_user_id="op-a", expected_version=1, now=T0)
            ctrl_a = get_conversation_control(db, tenant_a, conv_a)
            ctrl_b = get_conversation_control(db, tenant_b, conv_b)
            self.assertEqual((ctrl_a["mode"], ctrl_a["owner_user_id"]), ("human_active", "op-a"))
            self.assertEqual((ctrl_b["mode"], ctrl_b["owner_user_id"]), ("ai_active", None))
