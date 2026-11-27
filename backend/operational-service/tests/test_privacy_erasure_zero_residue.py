"""PRV-003 / QG-1: Negative zero-PII-residue test across all tenant tables after /erase."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext, quote_identifier
from app.public_models.tenant_runtime import TenantRuntime
from app.services.consent_authorization_service import evaluate_persisted_consent
from app.services.privacy_case_service import execute_privacy_erasure
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.domain_events import DomainEvent
from app.tenant_models.operations import Cliente, Conversation, Lead, Message, SolicitudDerecho
from app.tenant_models.opportunity import Opportunity, OpportunityActivity, PipelineStage
from app.tenant_models.phase5_integrations import ExternalEntityMapping
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 27, 10, 0, tzinfo=timezone.utc)
# Legal proof ledgers intentionally retain suppression/consent destination hashes/records.
LEGAL_PROOF_TABLES = {"contact_suppressions", "contact_consent_decisions"}


class PrivacyErasureZeroResidueTests(PostgresCase):
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
            db.add(
                TenantRuntime(
                    auth_tenant_id=auth_id,
                    tenant_slug=schema,
                    schema_name=schema,
                    tenant_code=schema,
                    ingest_key_hash="unused",
                    plan="pro",
                    status="active",
                )
            )
            db.commit()
        return tenant

    def test_erase_leaves_zero_pii_residue_across_all_tenant_tables_and_suppresses_email_and_whatsapp(self):
        tenant = self._seed_tenant("tenant_prv003_zero", 9801)
        rut = "12345678-5"
        email = "titular.prv003@example.test"
        phone = "+56987654321"
        wa_id = "56987654321"
        secret_msg = "Hola, mi RUT es 12345678-5 y mi correo titular.prv003@example.test"

        with Session(self.engine) as db:
            bind_tenant_session(db, tenant.schema_name)
            client = Cliente(
                id=1,
                rut=rut,
                nombre="Camila Titular",
                email=email,
                telefono=phone,
                whatsapp_id=wa_id,
                consentimiento_datos=True,
            )
            db.add(client)
            db.flush()

            conv = Conversation(id=1, session_id=wa_id, message={"channel": "whatsapp", "text": secret_msg})
            stage = PipelineStage(id=1, slug="nuevo", name="Nuevo", position=0, stage_kind="open")
            db.add_all([conv, stage])
            db.flush()

            lead = Lead(id=1, cliente_id=1, requiere_credito=True, resumen_ia=f"Interesada: {email} / {rut}")
            db.add(lead)
            db.flush()

            opp = Opportunity(id=1, contact_id=1, lead_id=1, conversation_id=1, stage_id=1, title="Venta")
            db.add(opp)
            db.flush()

            db.add_all([
                ContactPoint(id=1, client_id=1, point_type="email", normalized_value=email, status="active", verified=True),
                Message(id=1, whatsapp_id=wa_id, rol="usuario", direction="inbound", mensaje=secret_msg, creado_en=T0, recorded_at=T0),
                OpportunityActivity(id=1, opportunity_id=1, activity_type="note", note=f"Llamar a {phone} ({rut})", metadata_json={"email": email}),
                AIActionProposal(
                    id=1,
                    action_type="crm.contact.rename",
                    resource_type="contact",
                    resource_id=1,
                    arguments_json={"email": email, "rut": rut},
                    arguments_hash="h1",
                    idempotency_key="idem-prv003-1",
                    proposed_by="agent-core",
                    rationale=f"Solicitado por {email}",
                    expires_at=T0 + timedelta(hours=24),
                ),
                DomainEvent(
                    event_id="evt-prv003-1",
                    event_type="contact.created",
                    aggregate_type="contact",
                    aggregate_id="1",
                    payload={"rut": rut, "email": email, "phone": phone},
                ),
                ExternalEntityMapping(
                    connection_ref="hubspot",
                    resource_type="contact",
                    remote_id=f"ext-{rut}",
                    local_type="contact",
                    local_id="1",
                    conflict_payload={"email": email},
                ),
                SolicitudDerecho(
                    id=1,
                    whatsapp_id=wa_id,
                    tipo_derecho="eliminacion",
                    estado="en_proceso",
                    notas=f"Titular {email} RUT {rut}",
                ),
            ])
            db.commit()

            erased = execute_privacy_erasure(db, tenant, 1, actor_id="dpo-1", confirmed=True)
            self.assertEqual(erased["state"], "completada")
            self.assertEqual(erased["clients_anonymized"], 1)
            self.assertEqual(erased["email_suppressions_recorded"], 1)
            self.assertGreaterEqual(erased["conversations_redacted"], 1)
            self.assertGreaterEqual(erased["leads_redacted"], 1)
            self.assertGreaterEqual(erased["activities_redacted"], 1)
            self.assertGreaterEqual(erased["proposals_redacted"], 1)
            self.assertGreaterEqual(erased["domain_events_redacted"], 1)
            self.assertGreaterEqual(erased["external_mappings_deleted"], 1)

            # Verify RUT was irreversibly pseudonymized with anon-<sha256-prefix>.
            bind_tenant_session(db, tenant.schema_name)
            anon_client = db.get(Cliente, 1)
            self.assertTrue(anon_client.rut.startswith("anon-"))
            self.assertNotIn(rut, anon_client.rut)

            # Verify BOTH whatsapp and email suppressions are active.
            check_time = datetime.now(timezone.utc) + timedelta(seconds=1)
            self.assertEqual(
                evaluate_persisted_consent(db, tenant, client_id=1, channel="whatsapp", destination=wa_id, purpose="marketing", now=check_time),
                "suppressed",
            )
            self.assertEqual(
                evaluate_persisted_consent(db, tenant, client_id=1, channel="email", destination=email, purpose="marketing", now=check_time),
                "suppressed",
            )

            # Scan EVERY table in the tenant schema (except legal proof ledgers) for any PII residue.
            needles = (rut, email, phone, wa_id, "Camila Titular", secret_msg)
            quoted_schema = quote_identifier(tenant.schema_name)
            tables = inspect(db.connection()).get_table_names(schema=tenant.schema_name)
            leaks: list[str] = []
            for tbl in tables:
                if tbl in LEGAL_PROOF_TABLES:
                    continue
                rows = db.execute(text(f"SELECT * FROM {quoted_schema}.{quote_identifier(tbl)}")).fetchall()
                for row in rows:
                    row_text = " ".join(str(val) for val in row if val is not None)
                    for needle in needles:
                        if needle in row_text:
                            leaks.append(f"{tbl}: found '{needle}'")
            self.assertEqual(leaks, [], f"PII residue found after /erase: {leaks}")
