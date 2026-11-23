from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.services.ai_extensions_service import (
    apply_contact_enrichment,
    enqueue_external_notification,
    list_conversation_memory,
    propose_contact_enrichment,
    purge_expired_memory,
    record_ai_usage,
    record_conversation_memory,
    record_notification_receipt,
    summarize_ai_usage,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.operations import Cliente, Conversation
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 18, 0, tzinfo=timezone.utc)
T_EXPIRED = T0 + timedelta(days=31)


class AIExtensionsTests(PostgresCase):
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
                Cliente(id=1, rut=f"r-{auth_id}", nombre="Contacto Base", email=None),
                Conversation(id=1, session_id="56900001", message={"channel": "whatsapp"}),
                Conversation(id=2, session_id="56900002", message={"channel": "whatsapp"}),
            ])
            db.commit()
        return tenant

    def test_fk20_scoped_conversation_memory_and_retention(self):
        tenant = self._seed_tenant("tenant_fk20_mem", 2001)
        with Session(self.engine) as db:
            record_conversation_memory(
                db, tenant, 1, memory_key="budget", memory_value="20M CLP", source_type="message", source_ref="msg:10", ttl_days=30, now=T0,
            )
            # Conversation 2 must not see Conversation 1's memory.
            self.assertEqual(len(list_conversation_memory(db, tenant, 1, now=T0)), 1)
            self.assertEqual(list_conversation_memory(db, tenant, 2, now=T0), [])

            # After TTL expires, memory is excluded and purged cleanly.
            self.assertEqual(list_conversation_memory(db, tenant, 1, now=T_EXPIRED), [])
            self.assertEqual(purge_expired_memory(db, tenant, now=T_EXPIRED), 1)

    def test_fk21_confirmed_enrichment_conflict_control(self):
        tenant = self._seed_tenant("tenant_fk21_enr", 2002)
        with Session(self.engine) as db:
            # Empty email field -> applies cleanly.
            c1 = propose_contact_enrichment(db, tenant, 1, field_name="email", proposed_value="nuevo@Example.TEST", source="agent-core", now=T0)
            applied = apply_contact_enrichment(db, tenant, c1["id"], reviewer_user_id="op-1", now=T0)
            self.assertEqual((applied["status"], applied["proposed_value"]), ("applied", "nuevo@example.test"))

            # Conflicting email without allow_overwrite -> 409 and marks conflict.
            c2 = propose_contact_enrichment(db, tenant, 1, field_name="email", proposed_value="otro@example.test", source="agent-core", now=T0)
            with self.assertRaises(HTTPException) as ctx:
                apply_contact_enrichment(db, tenant, c2["id"], reviewer_user_id="op-1", allow_overwrite=False, now=T0)
            self.assertEqual(ctx.exception.status_code, 409)

    def test_fk25_external_notification_dedup_and_receipt_and_fk26_ai_usage(self):
        tenant = self._seed_tenant("tenant_fk25_26", 2003)
        with Session(self.engine) as db:
            n1 = enqueue_external_notification(
                db, tenant, dedup_key="handoff:1", event_type="conversation.handoff.requested",
                channel="email", recipient="ops@acme.test", payload={"conv": 1}, actor_user_id="sys", now=T0,
            )
            n2 = enqueue_external_notification(
                db, tenant, dedup_key="handoff:1", event_type="conversation.handoff.requested",
                channel="email", recipient="ops@acme.test", payload={"conv": 1}, actor_user_id="sys", now=T0,
            )
            self.assertFalse(n1["duplicate"])
            self.assertTrue(n2["duplicate"])
            self.assertEqual(n1["id"], n2["id"])

            delivered = record_notification_receipt(db, tenant, n1["id"], status_value="delivered", receipt_ref="rcpt-1", now=T0)
            self.assertEqual((delivered["status"], delivered["receipt_ref"]), ("delivered", "rcpt-1"))

            # FK-26: AI usage & cost ledger.
            record_ai_usage(
                db, tenant, provider="groq", model="llama-3.3-70b", prompt_tokens=500, completion_tokens=150,
                latency_ms=420, estimated_cost_usd=Decimal("0.001250"), now=T0,
            )
            record_ai_usage(
                db, tenant, provider="groq", model="llama-3.3-70b", prompt_tokens=300, completion_tokens=100,
                latency_ms=380, estimated_cost_usd=Decimal("0.000750"), now=T0,
            )
            summary = summarize_ai_usage(db, tenant, days=30, now=T0)
            self.assertEqual((summary["requests"], summary["prompt_tokens"], summary["completion_tokens"]), (2, 800, 250))
            self.assertEqual(Decimal(summary["total_cost_usd"]), Decimal("0.002000"))
