from datetime import datetime, timezone
import os
from statistics import quantiles
from time import perf_counter
from unittest import skipUnless
from unittest.mock import patch

from sqlalchemy import event, text, update
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import CurrentPrincipal, get_current_principal
from app.core.tenant_resolver import quote_identifier
from app.main import app
from app.public_models.tenant_runtime import TenantRuntime
from app.services.analytics_service import analytics_summary
from app.services.conversation_service import get_conversation, list_conversations, mark_conversation_read
from app.services.tenant_data import tenant_exec_options
from app.tenant_models.operations import Cliente, Conversation, Lead
from test_message_identity import PostgresCase
import test_turn_recovery


class ConversationInboxTests(PostgresCase):
    def call(self, fn, tenant, *args, **kwargs):
        with Session(self.engine) as db:
            return fn(db, tenant, *args, **kwargs)

    def insert(self, tenant, key, phone="12025550138", **payload):
        return self.ingest(tenant, self.payload(external_message_id=key, phone=phone, **payload))

    def seed(self, tenant, threads, messages_per_thread):
        schema = quote_identifier(tenant.schema_name)
        with self.engine.begin() as db:
            db.execute(text("SET LOCAL statement_timeout = '60s'"))
            db.execute(text(f"""
                INSERT INTO {schema}.clientes (rut, whatsapp_id, nombre, telefono)
                SELECT 'test-' || i, '12025' || lpad(i::text, 6, '0'),
                       'Contacto sintético ' || i, '12025' || lpad(i::text, 6, '0')
                FROM generate_series(1, :threads) AS i
            """), {"threads": threads})
            db.execute(text(f"""
                INSERT INTO {schema}.leads (cliente_id)
                SELECT id FROM {schema}.clientes
            """))
            db.execute(text(f"""
                INSERT INTO {schema}.conversaciones (session_id, message)
                SELECT whatsapp_id, '{{"channel":"whatsapp"}}'::jsonb FROM {schema}.clientes
                ORDER BY id
            """))
            db.execute(text(f"""
                INSERT INTO {schema}.mensajes_dashboard (whatsapp_id, rol, direction, mensaje, creado_en)
                SELECT session_id, 'usuario', 'inbound', 'Texto sintético ' || n,
                       TIMESTAMPTZ '2026-01-01T00:00:00Z' + id * INTERVAL '1 minute'
                FROM {schema}.conversaciones CROSS JOIN generate_series(1, :messages) AS n
            """), {"messages": messages_per_thread})
        with self.engine.begin() as db:
            for table in ("clientes", "conversaciones", "conversaciones_resumen", "leads", "mensajes_dashboard"):
                db.execute(text(f"ANALYZE {schema}.{table}"))

    def test_searches_beyond_page_one_and_keeps_derived_filters(self):
        tenant, other = self.tenant(), self.tenant()
        self.seed(tenant, 120, 1)
        self.insert(other, "hidden", full_name="Contacto sintético ajeno")
        first, count = self.call(list_conversations, tenant, 40, 0)
        self.assertEqual(count, 120)
        items, count = self.call(list_conversations, tenant, 50, 0, search="Contacto sintético 1")
        contact = next(item for item in items if item["lead_name"].endswith(" 1"))
        self.assertNotIn(contact["id"], {item["id"] for item in first})
        self.assertNotIn("Contacto sintético ajeno", [item["lead_name"] for item in items])
        self.assertEqual(self.call(list_conversations, tenant, 5, 0, search="%")[1], 0)
        self.assertEqual(self.call(list_conversations, tenant, 5, 0, search="Texto sintético")[1], 120)
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.execute(update(Lead).where(Lead.id == contact["lead_id"]).values(estado_seguimiento="requiere_humano"))
            db.execute(update(Conversation).where(Conversation.id == contact["id"]).values(message={"status": "closed"}))
            db.commit()
        filtered, total = self.call(list_conversations, tenant, 5, 0, "waiting", "whatsapp", True)
        self.assertEqual(total, 1)
        self.assertEqual(filtered[0]["id"], contact["id"])
        self.assertTrue(filtered[0]["requires_human"])

    def test_cursor_remains_stable_when_new_conversation_is_inserted(self):
        tenant = self.tenant()
        for index in range(5):
            self.insert(tenant, f"in-{index}", f"1202555014{index}")
        top, _ = self.call(list_conversations, tenant, 2, 0)
        tail = top[-1]
        self.insert(tenant, "newer", "12025550149", sent_at=datetime(2026, 1, 2, tzinfo=timezone.utc))
        page, total = self.call(list_conversations, tenant, 10, 0, before=(tail["last_message_at"], tail["id"]))
        self.assertEqual(total, 6)
        self.assertEqual([item["id"] for item in top + page], [5, 4, 3, 2, 1])

    def test_analytics_matches_inbox_threads_instead_of_lead_counts(self):
        tenant, other = self.tenant(), self.tenant()
        waiting = self.insert(tenant, "waiting", "12025550138")
        closed = self.insert(tenant, "closed", "12025550139")
        self.insert(other, "hidden", "12025550138")
        with Session(self.engine.execution_options(**tenant_exec_options(tenant.schema_name))) as db:
            db.get(Conversation, waiting["conversation_id"]).message = {"status": " Waiting "}
            db.get(Conversation, closed["conversation_id"]).message = {"status": "closed"}
            db.add(Conversation(session_id="12025550138", message={"status": "active"}))
            db.add(Lead(cliente=Cliente(rut="no-thread", nombre="Lead sin conversación")))
            db.commit()

        statements = []

        def collect(_conn, _cursor, statement, *_):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", collect)
        try:
            counts = self.call(analytics_summary, tenant)
        finally:
            event.remove(self.engine, "before_cursor_execute", collect)
        self.assertEqual(len(statements), 1)
        inbox, total = self.call(list_conversations, tenant, 10, 0)
        self.assertEqual(total, 2)
        self.assertEqual(counts["total_leads"], 3)
        self.assertEqual(counts["open_conversations"], 1)
        self.assertEqual(counts["requires_human"], 1)
        self.assertEqual(counts["open_conversations"], sum(item["status"] != "closed" for item in inbox))
        self.assertEqual(counts["requires_human"], sum(item["requires_human"] for item in inbox))

    def test_analytics_message_windows_exclude_future_and_expired_timestamps(self):
        tenant = self.tenant()
        now = datetime(2026, 1, 8, 12, tzinfo=timezone.utc)
        for identifier, sent_at in (
            ("today", datetime(2026, 1, 8, tzinfo=timezone.utc)),
            ("week-start", datetime(2026, 1, 1, 12, tzinfo=timezone.utc)),
            ("outside-week", datetime(2026, 1, 1, 11, 59, tzinfo=timezone.utc)),
            ("future", datetime(2026, 1, 8, 13, tzinfo=timezone.utc)),
        ):
            self.insert(tenant, identifier, sent_at=sent_at)

        with patch("app.services.analytics_service.datetime") as clock:
            clock.now.return_value = now
            counts = self.call(analytics_summary, tenant)

        self.assertEqual(counts["messages_today"], 1)
        self.assertEqual(counts["messages_last_7_days"], 2)

    def test_shared_read_is_monotonic_and_keeps_new_arrivals_and_agent_replies(self):
        tenant = self.tenant()
        first = self.insert(tenant, "in-1")
        second = self.insert(tenant, "in-2")
        chat_id = first["conversation_id"]
        self.insert(tenant, "out", direction="outbound")
        self.assertEqual(self.call(get_conversation, tenant, chat_id)["no_leidos"], 2)
        foreign_thread = self.insert(tenant, "other-thread", "12025550139")
        self.assertIsNone(self.call(mark_conversation_read, tenant, chat_id, foreign_thread["message_id"]))
        self.assertEqual(self.call(mark_conversation_read, tenant, chat_id, first["message_id"]), 1)
        self.assertEqual(self.call(mark_conversation_read, tenant, chat_id, second["message_id"]), 0)
        self.insert(tenant, "arrived-later")
        self.assertEqual(self.call(mark_conversation_read, tenant, chat_id, first["message_id"]), 1)
        self.assertEqual(self.call(get_conversation, tenant, chat_id)["no_leidos"], 1)
        self.assertIsNone(self.call(mark_conversation_read, self.tenant(), chat_id, first["message_id"]))

    def test_read_http_requires_crm_permission(self):
        tenant = self.tenant()
        first = self.insert(tenant, "in-1")
        with Session(self.engine) as db:
            db.add(TenantRuntime(auth_tenant_id=811, schema_name=tenant.schema_name, tenant_slug=tenant.tenant_slug,
                                 tenant_code=tenant.tenant_code, ingest_key_hash="unused", status="active", plan="free"))
            db.commit()

        def sessions():
            with Session(self.engine) as db:
                yield db

        permissions = ["users.read"]

        def principal():
            return CurrentPrincipal("user-test", 811, None, [], permissions, {}, {})

        app.dependency_overrides[get_db] = sessions
        app.dependency_overrides[get_current_principal] = principal
        self.addCleanup(app.dependency_overrides.clear)
        http = test_turn_recovery.TurnRecoveryTests.http
        base = "/api/v1/conversations"
        status, listed, _ = http(self, "GET", base)
        self.assertEqual(status, 200)
        self.assertEqual(listed["data"]["items"][0]["no_leidos"], 1)
        path = f"{base}/{first['conversation_id']}/read"
        payload = {"through_message_id": first["message_id"]}
        self.assertEqual(http(self, "POST", path, payload)[0], 403)
        permissions.append("crm.manage")
        status, result, _ = http(self, "POST", path, payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["data"]["no_leidos"], 0)

    @skipUnless(os.getenv("FLOWKRON_TEST_INBOX_BENCHMARK") == "1", "Set FLOWKRON_TEST_INBOX_BENCHMARK=1 for volume checks")
    def test_inbox_query_budget(self):
        tenant = self.tenant()
        self.seed(tenant, 10_000, 10)
        statements = []

        def collect(_connection, _cursor, statement, parameters, _context, _many):
            statements.append((statement, parameters))

        for search in (None, "Contacto sintético 42"):
            self.call(list_conversations, tenant, 40, 0, search=search)
            samples = []
            for _ in range(20):
                started = perf_counter()
                items, _ = self.call(list_conversations, tenant, 40, 0, search=search)
                samples.append(1000 * (perf_counter() - started))
            self.assertTrue(items)
            p95 = quantiles(samples, n=20, method="inclusive")[18]
            print(f"\nInbox {'search' if search else 'first page'} p95 {p95:.1f} ms")
            event.listen(self.engine, "before_cursor_execute", collect)
            try:
                self.call(list_conversations, tenant, 40, 0, search=search)
            finally:
                event.remove(self.engine, "before_cursor_execute", collect)
            with self.engine.connect() as db:
                for statement, parameters in statements:
                    plan = db.exec_driver_sql("EXPLAIN (ANALYZE, BUFFERS) " + statement, parameters).scalars()
                    print("\n".join(plan))
            statements.clear()
            self.assertLess(p95, 250)
