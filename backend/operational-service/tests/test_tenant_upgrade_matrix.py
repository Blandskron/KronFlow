from datetime import UTC, datetime
from unittest.mock import patch

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema

from app.core.config import get_settings
from app.core.database import Base
from app.core.tenant_resolver import quote_identifier
from app.public_models.migration_registry import MigrationRegistry
from app.public_models.system_event import SystemEvent
from app.public_models.tenant_runtime import TenantRuntime
from app.services.tenant_data import tenant_exec_options
from app.services.tenant_provisioning_service import migrate_all_tenants, migrate_runtime
from app.tenant_models.context import TenantAgentProfile
from app.tenant_models.operations import ACTIVE_TENANT_TABLE_NAMES, Cliente, Conversation, Lead, Message
from app.tenant_models.whatsapp_consent import WhatsAppConsentState
from app.tenant_models.whatsapp_turn import WhatsAppSendEvidence, WhatsAppTurn, WhatsAppTurnJob
from test_message_identity import PostgresCase


TABLE_INTRODUCED = {
    "whatsapp_turns": 4,
    "whatsapp_turn_jobs": 5,
    "whatsapp_send_evidence": 7,
    "whatsapp_consent_state": 8,
    "action_outbox_jobs": 9,
    "contact_consent_decisions": 9,
    "contact_suppressions": 9,
    "conversation_controls": 10,
    "conversation_control_events": 10,
    "tenant_ai_policies": 10,
    "pipeline_stages": 11,
    "opportunities": 11,
    "opportunity_activities": 11,
    "ai_action_proposals": 12,
    "contact_points": 13,
    "lead_captures": 13,
    "domain_events": 13,
    "domain_event_subscriptions": 13,
    "tenant_channel_connections": 14,
    "message_templates": 14,
    "template_versions": 14,
    "campaigns": 14,
    "campaign_approvals": 14,
    "campaign_recipients": 14,
    "delivery_attempts": 14,
    "channel_events": 14,
    "conversation_memory_items": 15,
    "contact_enrichment_candidates": 15,
    "external_notification_deliveries": 15,
    "ai_usage_records": 15,
    "webhook_subscriptions": 16,
    "webhook_deliveries": 16,
    "private_attachments": 16,
    "calendar_appointments": 16,
    "agent_revisions": 17,
    "agent_rules": 17,
    "agent_execution_traces": 17,
    "setup_chat_sessions": 17,
    "workflow_definitions": 18,
    "workflow_revisions": 18,
    "workflow_runs": 18,
    "workflow_step_runs": 18,
    "tool_definitions": 19,
    "tool_invocations": 19,
    "webchat_sessions": 19,
    "external_entity_mappings": 20,
    "connector_sync_cursors": 20,
    "commerce_orders": 21,
    "commerce_payment_events": 21,
    "voice_call_sessions": 21,
    "voice_call_segments": 21,
    "remote_mcp_servers": 21,
    "tenant_retention_policies": 22,
    "tenant_subprocessor_approvals": 22,
}
DECISION_AT = datetime(2026, 1, 1, tzinfo=UTC)
EXISTING_BOUNDARY = datetime(2025, 12, 31, tzinfo=UTC)
PHONE = "12025550138"


class TenantUpgradeMatrixTests(PostgresCase):
    def seed_version(self, version: int, auth_id: int, status: str = "active") -> str:
        name = f"tenant_fk15_v{version}_{auth_id}"
        tables = [table for table in Base.metadata.sorted_tables
                  if table.schema == "tenant" and table.name in ACTIVE_TENANT_TABLE_NAMES
                  and TABLE_INTRODUCED.get(table.name, 3) <= version]
        with self.engine.begin() as connection:
            connection.execute(CreateSchema(name))
            Base.metadata.create_all(connection.execution_options(**tenant_exec_options(name)), tables=tables)
            if version >= 6:
                table = f"{quote_identifier(name)}.mensajes_dashboard"
                connection.execute(text(f"CREATE INDEX idx_messages_thread_id ON {table} (whatsapp_id, id)"))

        with Session(self.engine.execution_options(**tenant_exec_options(name))) as db:
            db.add_all([
                Cliente(id=1, rut="synthetic-fk15", nombre=name, whatsapp_id=PHONE, consentimiento_datos=False),
                Conversation(id=1, session_id=PHONE, message={"channel": "whatsapp"}),
                Message(id=1, whatsapp_id=PHONE, rol="usuario", direction="inbound", mensaje=name,
                        external_message_id="same-id-across-workspaces"),
                SystemEvent(auth_tenant_id=auth_id, schema_name=name, event_type="whatsapp.consent.changed",
                            payload={"client_id": 1}, created_at=DECISION_AT),
                TenantRuntime(auth_tenant_id=auth_id, tenant_slug=name, schema_name=name, tenant_code=name,
                              ingest_key_hash="unused", plan="free", status=status),
                MigrationRegistry(schema_name=name, migration_version=f"tenant_schema_v{version}", status="success"),
            ])
            db.flush()
            db.add(Lead(id=1, cliente_id=1))
            db.add(TenantAgentProfile(tenant_id=str(auth_id), name=f"Legacy Agent {version}"))
            db.flush()
            if version >= 4:
                db.add(WhatsAppTurn(id=1, lead_id=1, conversation_id=1, phone=PHONE, state="prepared", reply_body="synthetic"))
                db.flush()
            if version >= 5:
                db.add(WhatsAppTurnJob(turn_id=1, account_key="synthetic", recipient_jid=f"{PHONE}@s.whatsapp.net"))
                db.flush()
            if version >= 7:
                db.add(WhatsAppSendEvidence(turn_id=1, account_key="synthetic", provider_message_id="evidence-1",
                                            status="unknown", started_at=DECISION_AT))
            if version >= 8:
                db.add(WhatsAppConsentState(client_id=1, decision_at=EXISTING_BOUNDARY))
            db.commit()
        return name

    def test_active_matrix_is_repeatable_and_suspended_upgrade_is_transactional(self):
        matrix = {version: self.seed_version(version, version) for version in range(3, 23)}
        suspended = self.seed_version(3, 99, status="suspended")
        for _ in range(2):
            with Session(self.engine) as db:
                result = migrate_all_tenants(db)
                self.assertEqual((result["total"], result["success"], result["failed"]), (20, 20, 0), result)
        self.assertFalse(inspect(self.engine).has_table("whatsapp_turns", schema=suspended))

        for version, schema in matrix.items():
            with self.subTest(version=version), Session(self.engine.execution_options(**tenant_exec_options(schema))) as db:
                self.assertEqual(set(inspect(self.engine).get_table_names(schema=schema)), ACTIVE_TENANT_TABLE_NAMES)
                indexes = inspect(self.engine).get_indexes("mensajes_dashboard", schema=schema)
                self.assertIn("idx_messages_thread_id", {index["name"] for index in indexes})
                self.assertEqual(db.execute(select(Lead.id, Lead.cliente_id)).all(), [(1, 1)])
                agent_profile = db.scalar(select(TenantAgentProfile).where(TenantAgentProfile.tenant_id == str(version)))
                self.assertIsNotNone(agent_profile)
                self.assertTrue(agent_profile.is_default)
                self.assertEqual(db.execute(select(Message.id, Message.mensaje, Message.external_message_id)).all(),
                                 [(1, schema, "same-id-across-workspaces")])
                self.assertEqual(db.scalars(select(WhatsAppTurn.id)).all(), [1] if version >= 4 else [])
                self.assertEqual(db.scalars(select(WhatsAppTurnJob.turn_id)).all(), [1] if version >= 5 else [])
                self.assertEqual(db.scalars(select(WhatsAppSendEvidence.provider_message_id)).all(), ["evidence-1"] if version >= 7 else [])
                self.assertEqual(db.get(WhatsAppConsentState, 1).decision_at, EXISTING_BOUNDARY if version >= 8 else DECISION_AT)
                rows = db.scalars(select(MigrationRegistry).where(
                    MigrationRegistry.schema_name == schema,
                    MigrationRegistry.migration_version == get_settings().tenant_migration_version,
                )).all()
                self.assertEqual([row.status for row in rows], ["success"])

        with Session(self.engine) as db:
            runtime = db.scalar(select(TenantRuntime).where(TenantRuntime.schema_name == suspended))
            with patch("app.services.tenant_provisioning_service.apply_tenant_database_objects",
                       side_effect=SQLAlchemyError("Synthetic late failure")):
                self.assertEqual(migrate_runtime(db, runtime)["status"], "failed")
            self.assertFalse(inspect(self.engine).has_table("whatsapp_turns", schema=suspended))
            self.assertEqual(migrate_runtime(db, runtime)["status"], "success")
            self.assertEqual(runtime.status, "suspended")
        with Session(self.engine.execution_options(**tenant_exec_options(suspended))) as db:
            self.assertEqual(db.get(Message, 1).mensaje, suspended)
            self.assertEqual(db.get(WhatsAppConsentState, 1).decision_at, DECISION_AT)
