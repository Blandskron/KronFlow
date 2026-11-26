from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.agent import AgentConfigureRequest
from app.schemas.commerce import CommerceOrderCreateIn
from app.schemas.contact import ContactMergeIn
from app.schemas.conversation import AgentHandoffIn
from app.schemas.voice import VoiceCallCreateIn
from app.services.agent_handoff_service import handoff_conversation_to_agent, list_conversation_agent_handoffs
from app.services.agent_service import configure_agent, publish_agent
from app.services.campaign_service import create_campaign, create_template_with_version, preview_campaign_audience
from app.services.channel_connection_service import create_channel_connection
from app.services.commerce_service import create_commerce_order
from app.services.consent_authorization_service import evaluate_persisted_consent, record_consent_decision, record_suppression
from app.services.contact_merge_service import merge_contacts
from app.services.conversation_control_service import get_conversation_control
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.services.voice_service import start_voice_call
from app.tenant_models.action_outbox import ActionOutboxJob
from app.tenant_models.campaigns import CampaignRecipient
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.operations import Cliente, Conversation, Lead
from app.tenant_models.opportunity import Opportunity, PipelineStage
from app.tenant_models.phase6_extensions import CommerceOrder, VoiceCallSession
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 26, 21, 0, tzinfo=timezone.utc)


class MergePreviewHandoffTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int) -> TenantContext:
        tenant = TenantContext(
            auth_tenant_id=auth_id,
            tenant_slug=schema,
            schema_name=schema,
            tenant_code=schema,
            plan="pro",
            status="active",
        )
        with Session(self.engine) as db:
            apply_tenant_schema(db, schema)
            db.commit()
        return tenant

    def test_authorized_contact_merge_preserves_history_and_suppressions(self):
        tenant = self._seed_tenant("tenant_p7_merge", 9601)
        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            src = Cliente(rut="src-1", nombre="Origen", whatsapp_id="56970001")
            dst = Cliente(rut="dst-1", nombre="Destino", email="dst@acme.test")
            db.add_all([src, dst])
            db.flush()

            stage = PipelineStage(slug="nuevo", name="Nuevo", position=1)
            db.add(stage)
            db.flush()

            db.add(Lead(cliente_id=src.id, estado="nuevo", clasificacion="tibio"))
            db.add(Opportunity(contact_id=src.id, stage_id=stage.id, title="Opp Src", currency="CLP", owner_user_id="u1"))
            db.add(ContactPoint(client_id=src.id, point_type="whatsapp", normalized_value="56970001", verified=True))
            db.add(ContactPoint(client_id=dst.id, point_type="email", normalized_value="dst@acme.test", verified=True))
            db.commit()

            create_commerce_order(
                db,
                tenant,
                CommerceOrderCreateIn(provider="stub", client_id=src.id, currency="CLP", expected_amount_minor=9900),
                actor_user_id="mgr-1",
                now=T0,
            )
            start_voice_call(
                db,
                tenant,
                VoiceCallCreateIn(
                    provider="stub",
                    external_call_id="merge-call-1",
                    from_number="+56970001",
                    to_number="+5620001",
                    client_id=src.id,
                ),
                now=T0,
            )
            record_suppression(
                db,
                tenant,
                client_id=src.id,
                channel="whatsapp",
                destination="56970001",
                purpose="marketing",
                reason="unsubscribe",
                source="unsubscribe_link",
                recorded_at=T0,
            )

            with self.assertRaises(HTTPException) as unconf:
                merge_contacts(
                    db,
                    tenant,
                    src.id,
                    ContactMergeIn(target_contact_id=dst.id, confirmed=False),
                    actor_user_id="mgr-1",
                    now=T0,
                )
            self.assertEqual(unconf.exception.status_code, 422)

            with self.assertRaises(HTTPException) as same_err:
                merge_contacts(
                    db,
                    tenant,
                    src.id,
                    ContactMergeIn(target_contact_id=src.id, confirmed=True),
                    actor_user_id="mgr-1",
                    now=T0,
                )
            self.assertEqual(same_err.exception.status_code, 422)

            merged = merge_contacts(
                db,
                tenant,
                src.id,
                ContactMergeIn(target_contact_id=dst.id, confirmed=True, reason="duplicate_customer"),
                actor_user_id="mgr-1",
                now=T0,
            )
            self.assertEqual(merged["leads_moved"], 1)
            self.assertEqual(merged["opportunities_moved"], 1)
            self.assertEqual(merged["suppressions_moved"], 1)
            self.assertEqual(merged["orders_moved"], 1)
            self.assertEqual(merged["voice_calls_moved"], 1)
            self.assertEqual(merged["contact_points_moved"], 1)

            bind_tenant_session(db, tenant.schema_name)
            self.assertIsNone(db.get(Cliente, src.id))
            dst_after = db.get(Cliente, dst.id)
            self.assertEqual(dst_after.whatsapp_id, "56970001")
            self.assertEqual(db.scalar(select(CommerceOrder).where(CommerceOrder.client_id == dst.id)).client_id, dst.id)
            self.assertEqual(db.scalar(select(VoiceCallSession).where(VoiceCallSession.client_id == dst.id)).client_id, dst.id)
            self.assertEqual(
                evaluate_persisted_consent(
                    db,
                    tenant,
                    client_id=dst.id,
                    channel="whatsapp",
                    destination="56970001",
                    purpose="marketing",
                    point_active=True,
                    point_verified=True,
                    now=T0,
                ),
                "suppressed",
            )

    def test_campaign_audience_preview_is_read_only_and_classifies_exclusions(self):
        tenant = self._seed_tenant("tenant_p7_preview", 9602)
        with Session(self.engine) as db:
            conn = create_channel_connection(
                db,
                tenant,
                channel="email",
                provider="stub",
                sender_address="noreply@acme.test",
                display_name="ACME",
                verified=True,
                sandbox_only=True,
                actor_user_id="mgr-1",
            )
            tmpl = create_template_with_version(
                db,
                tenant,
                name="Promo",
                channel="email",
                language="es",
                subject="Hola",
                body_text="Oferta",
                approve_immediately=True,
                actor_user_id="mgr-1",
            )
            camp = create_campaign(
                db,
                tenant,
                name="Preview Camp",
                channel="email",
                purpose="marketing",
                template_version_id=tmpl["template_version_id"],
                connection_id=conn["id"],
                timezone_iana="UTC",
                actor_user_id="mgr-1",
            )

            bind_tenant_session(db, tenant.schema_name)
            c1 = Cliente(rut="p1", nombre="Elegible")
            c2 = Cliente(rut="p2", nombre="NoVerificado")
            c3 = Cliente(rut="p3", nombre="Suprimido")
            c4 = Cliente(rut="p4", nombre="SinConsent")
            db.add_all([c1, c2, c3, c4])
            db.flush()
            db.add_all(
                [
                    ContactPoint(client_id=c1.id, point_type="email", normalized_value="ok@acme.test", verified=True),
                    ContactPoint(client_id=c2.id, point_type="email", normalized_value="unver@acme.test", verified=False),
                    ContactPoint(client_id=c3.id, point_type="email", normalized_value="sup@acme.test", verified=True),
                    ContactPoint(client_id=c4.id, point_type="email", normalized_value="noconsent@acme.test", verified=True),
                ]
            )
            db.commit()

            record_consent_decision(
                db,
                tenant,
                client_id=c1.id,
                channel="email",
                destination="ok@acme.test",
                purpose="marketing",
                granted=True,
                source="form",
                effective_at=T0,
            )
            record_consent_decision(
                db,
                tenant,
                client_id=c3.id,
                channel="email",
                destination="sup@acme.test",
                purpose="marketing",
                granted=True,
                source="form",
                effective_at=T0,
            )
            record_suppression(
                db,
                tenant,
                client_id=c3.id,
                channel="email",
                destination="sup@acme.test",
                purpose="marketing",
                reason="unsubscribe",
                source="unsubscribe_link",
                recorded_at=T0,
            )

            preview = preview_campaign_audience(db, tenant, camp["id"], now=T0)
            self.assertEqual(preview["total_candidates"], 4)
            self.assertEqual(preview["eligible_count"], 1)
            self.assertEqual(preview["excluded_count"], 3)
            self.assertEqual(preview["excluded_by_reason"]["unverified_point"], 1)
            self.assertEqual(preview["excluded_by_reason"]["suppressed"], 1)
            self.assertEqual(preview["excluded_by_reason"]["consent_missing"], 1)
            self.assertEqual(preview["sample_eligible"][0]["destination"], "ok@acme.test")

            bind_tenant_session(db, tenant.schema_name)
            self.assertEqual(db.scalar(select(func.count()).select_from(CampaignRecipient)), 0)
            self.assertEqual(db.scalar(select(func.count()).select_from(ActionOutboxJob)), 0)

    def test_specialist_agent_handoff_hop_limit_escalates_to_human(self):
        tenant = self._seed_tenant("tenant_p7_handoff", 9603)
        with Session(self.engine) as db:
            draft_agent = configure_agent(
                db,
                tenant,
                AgentConfigureRequest(name="Borrador", role="triage", instructions="Solo borrador"),
                now=T0,
            )
            spec_agent = configure_agent(
                db,
                tenant,
                AgentConfigureRequest(name="Especialista Agenda", role="scheduler", instructions="Agenda citas"),
                now=T0,
            )
            publish_agent(db, tenant, spec_agent["id"], expected_version=1, now=T0)

            bind_tenant_session(db, tenant.schema_name)
            conv = Conversation(session_id="conv-handoff-1", message={"channel": "webchat"})
            db.add(conv)
            db.commit()
            db.refresh(conv)

            with self.assertRaises(HTTPException) as draft_err:
                handoff_conversation_to_agent(
                    db,
                    tenant,
                    conv.id,
                    AgentHandoffIn(target_agent_id=draft_agent["id"], reason="need_triage"),
                    actor_user_id="agent-runtime",
                    now=T0,
                )
            self.assertEqual(draft_err.exception.status_code, 422)

            for expected_hop in (1, 2):
                res = handoff_conversation_to_agent(
                    db,
                    tenant,
                    conv.id,
                    AgentHandoffIn(
                        target_agent_id=spec_agent["id"],
                        from_agent_id=draft_agent["id"],
                        reason=f"hop_{expected_hop}",
                        shared_summary="Cliente solicita reunión",
                        max_hops=2,
                    ),
                    actor_user_id="agent-runtime",
                    now=T0,
                )
                self.assertEqual(res["hop_number"], expected_hop)
                self.assertEqual(res["to_agent_revision_id"], res["to_agent_revision_id"])

            history = list_conversation_agent_handoffs(db, tenant, conv.id)
            self.assertEqual([item["hop_number"] for item in history], [1, 2])

            with self.assertRaises(HTTPException) as limit_err:
                handoff_conversation_to_agent(
                    db,
                    tenant,
                    conv.id,
                    AgentHandoffIn(target_agent_id=spec_agent["id"], reason="loop_attempt", max_hops=2),
                    actor_user_id="agent-runtime",
                    now=T0,
                )
            self.assertEqual(limit_err.exception.status_code, 409)

            ctrl = get_conversation_control(db, tenant, conv.id)
            self.assertEqual(ctrl["mode"], "waiting_human")
            self.assertEqual(ctrl["handoff_reason"], "agent_handoff_hop_limit_exceeded")
