from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.analytics_service import analytics_kpis
from app.services.campaign_service import (
    approve_campaign,
    create_campaign,
    create_template_with_version,
    ingest_channel_receipt,
    process_campaign_stub_batch,
)
from app.services.channel_connection_service import create_channel_connection
from app.services.consent_authorization_service import evaluate_persisted_consent, record_consent_decision
from app.services.opportunity_service import create_opportunity, update_opportunity
from app.services.privacy_case_service import (
    execute_privacy_erasure,
    export_privacy_case_data,
    run_retention_sweep,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.campaigns import CampaignRecipient
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.operations import Cliente, Lead, LogLimpieza, Message, SolicitudDerecho
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 17, 0, tzinfo=timezone.utc)
T_OLD = T0 - timedelta(days=90)


class KpisAndPrivacyExecutionTests(PostgresCase):
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

    def test_fk09_consolidated_kpis_reconcile_pipeline_campaigns_events_and_isolate_tenants(self):
        tenant_a = self._seed_tenant("tenant_fk09_a", 9001)
        tenant_b = self._seed_tenant("tenant_fk09_b", 9002)

        with Session(self.engine) as db:
            # Empty tenant B returns None rates (zero denominator separated from zero activity).
            empty_kpis = analytics_kpis(db, tenant_b)
            self.assertIsNone(empty_kpis.pipeline.win_rate)
            self.assertIsNone(empty_kpis.campaigns.delivery_rate)
            self.assertEqual(empty_kpis.events.total_domain_events, 0)

            bind_tenant_session(db, tenant_a.schema_name)
            db.add(Cliente(id=1, rut="r1", nombre="Cliente KPI", email="kpi@example.test", whatsapp_id="56990001"))
            db.flush()
            db.add(ContactPoint(id=1, client_id=1, point_type="email", normalized_value="kpi@example.test", status="active", verified=True))
            db.commit()

            # Pipeline: 1 won (1000.00 USD) and 1 lost -> win_rate = 0.5
            o1 = create_opportunity(db, tenant_a, title="Won Deal", contact_id=1, amount=Decimal("1000.00"), currency="USD", actor_user_id="s1", now=T0)
            update_opportunity(db, tenant_a, o1["id"], expected_version=1, outcome="won", actor_user_id="s1", now=T0)
            o2 = create_opportunity(db, tenant_a, title="Lost Deal", contact_id=1, amount=Decimal("500.00"), currency="USD", actor_user_id="s1", now=T0)
            update_opportunity(db, tenant_a, o2["id"], expected_version=1, outcome="lost", close_reason="price", actor_user_id="s1", now=T0)

            # Campaign: 1 delivered out of 1 accepted -> delivery_rate = 1.0 + campaign.approved domain event
            record_consent_decision(
                db, tenant_a, client_id=1, channel="email", destination="kpi@example.test", purpose="marketing",
                granted=True, effective_at=T0, recorded_at=T0, source="form",
            )
            conn = create_channel_connection(
                db, tenant_a, channel="email", provider="stub", sender_address="hi@acme.test",
                display_name="Acme", verified=True, actor_user_id="a1", now=T0,
            )
            tmpl = create_template_with_version(
                db, tenant_a, name="T", channel="email", subject="S", body_text="B", approve_immediately=True, actor_user_id="a1", now=T0,
            )
            camp = create_campaign(
                db, tenant_a, name="C", channel="email", purpose="marketing",
                template_version_id=tmpl["template_version_id"], connection_id=conn["id"], actor_user_id="a1", now=T0,
            )
            approve_campaign(db, tenant_a, camp["id"], expected_version=1, actor_user_id="a1", now=T0)
            process_campaign_stub_batch(db, tenant_a, limit=10, now=T0)

            bind_tenant_session(db, tenant_a.schema_name)
            rec = db.scalar(select(CampaignRecipient).where(CampaignRecipient.campaign_id == camp["id"]))
            ingest_channel_receipt(
                db, tenant_a, provider_account_id="stub", provider_event_id="ev-kpi-1",
                event_type="delivered", provider_message_id=rec.provider_message_id, occurred_at=T0,
            )

            kpis_a = analytics_kpis(db, tenant_a)
            self.assertEqual((kpis_a.pipeline.won_opportunities, kpis_a.pipeline.lost_opportunities), (1, 1))
            self.assertEqual(kpis_a.pipeline.win_rate, 0.5)
            self.assertEqual(kpis_a.pipeline.won_amount_by_currency, {"USD": "1000.00"})
            self.assertEqual((kpis_a.campaigns.recipients_accepted, kpis_a.campaigns.recipients_delivered), (1, 1))
            self.assertEqual(kpis_a.campaigns.delivery_rate, 1.0)
            self.assertEqual(kpis_a.events.event_counts_by_type.get("campaign.approved"), 1)

            # Tenant B remains completely unaffected.
            self.assertEqual(analytics_kpis(db, tenant_b).pipeline.won_opportunities, 0)

    def test_fk27_privacy_export_erasure_and_retention_sweep(self):
        tenant = self._seed_tenant("tenant_fk27_priv", 9003)
        phone = "56927000001"

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            db.add(Cliente(id=1, rut="r27", nombre="Persona Real", email="real@example.test", telefono="+56927000001", whatsapp_id=phone, consentimiento_datos=True))
            db.flush()
            db.add_all([
                ContactPoint(id=1, client_id=1, point_type="email", normalized_value="real@example.test", status="active", verified=True),
                Lead(id=1, cliente_id=1),
                Message(id=1, whatsapp_id=phone, rol="usuario", direction="inbound", mensaje="Mensaje sensible", creado_en=T0, recorded_at=T0),
                Message(id=2, whatsapp_id="56999999999", rol="usuario", direction="inbound", mensaje="Mensaje antiguo", creado_en=T_OLD, recorded_at=T_OLD),
                SolicitudDerecho(id=1, whatsapp_id=phone, tipo_derecho="eliminacion", estado="pendiente"),
            ])
            db.commit()

            # Export collects full subject data.
            exported = export_privacy_case_data(db, tenant, 1, actor_id="dpo-1")
            self.assertEqual(exported["subject_contact"]["nombre"], "Persona Real")
            self.assertEqual(len(exported["contact_points"]), 1)
            self.assertEqual(exported["message_count"], 1)

            # Unconfirmed erasure is rejected (422).
            with self.assertRaises(HTTPException) as ctx_unconf:
                execute_privacy_erasure(db, tenant, 1, actor_id="dpo-1", confirmed=False)
            self.assertEqual(ctx_unconf.exception.status_code, 422)

            # Confirmed erasure anonymizes PII, deletes contact_points, redacts messages, suppresses, and logs LogLimpieza.
            erased = execute_privacy_erasure(db, tenant, 1, actor_id="dpo-1", confirmed=True)
            self.assertEqual(
                (erased["state"], erased["clients_anonymized"], erased["messages_redacted"], erased["contact_points_deleted"], erased["suppression_recorded"]),
                ("completada", 1, 1, 1, True),
            )
            bind_tenant_session(db, tenant.schema_name)
            anon_client = db.get(Cliente, 1)
            self.assertEqual((anon_client.nombre, anon_client.email, anon_client.consentimiento_datos), ("Anonimizado", None, False))
            self.assertEqual(db.get(Message, 1).mensaje, "[REDACTED_PRIVACY]")
            self.assertEqual(
                evaluate_persisted_consent(
                    db,
                    tenant,
                    client_id=1,
                    channel="whatsapp",
                    destination=phone,
                    purpose="marketing",
                    now=datetime.now(timezone.utc) + timedelta(seconds=1),
                ),
                "suppressed",
            )

            # Retention sweep deletes messages older than 30 days (message #2) and keeps recent message #1.
            swept = run_retention_sweep(db, tenant, message_retention_days=30, actor_id="dpo-1", now=T0)
            self.assertEqual(swept["messages_deleted"], 1)
            bind_tenant_session(db, tenant.schema_name)
            self.assertIsNone(db.get(Message, 2))
            self.assertIsNotNone(db.get(Message, 1))
            self.assertEqual(db.query(LogLimpieza).count(), 2)
