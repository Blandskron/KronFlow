from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.services.ai_proposal_service import (
    create_ai_proposal,
    execute_ai_proposal,
    get_ai_proposal,
    review_ai_proposal,
)
from app.services.opportunity_service import create_opportunity
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.operations import Cliente, Conversation, Lead
from app.tenant_models.opportunity import OpportunityActivity
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 14, 0, tzinfo=timezone.utc)
T_EXP = T0 + timedelta(minutes=30)
T_AFTER_EXP = T0 + timedelta(minutes=31)


class AIProposalTests(PostgresCase):
    def _seed_tenant(self, schema: str, auth_id: int, *, status: str = "active") -> TenantContext:
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
            db.add_all([
                Cliente(id=1, rut=f"rut-{auth_id}", nombre="Original Name", whatsapp_id=f"569111{auth_id}"),
                Conversation(id=1, session_id=f"569111{auth_id}", message={"channel": "whatsapp"}),
            ])
            db.flush()
            db.add(Lead(id=1, cliente_id=1))
            db.commit()
        return tenant

    def test_proposal_does_not_mutate_until_approved_and_executes_at_most_once(self):
        tenant = self._seed_tenant("tenant_fk17_exec", 1701)

        with Session(self.engine) as db:
            opp = create_opportunity(db, tenant, title="Deal IA", contact_id=1, actor_user_id="rep-1", now=T0)

            # Unsupported action type is rejected.
            with self.assertRaises(HTTPException) as ctx_bad:
                create_ai_proposal(
                    db, tenant, action_type="shell.exec", resource_id=1, arguments={"cmd": "rm"}, idempotency_key="bad", proposed_by="agent", now=T0,
                )
            self.assertEqual(ctx_bad.exception.status_code, 422)

            # Create typed proposal -> CRM resource must remain unchanged.
            prop = create_ai_proposal(
                db,
                tenant,
                action_type="crm.opportunity.add_note",
                resource_id=opp["id"],
                arguments={"note": "Cliente solicitó financiamiento a 24 cuotas"},
                idempotency_key="prop-note-1",
                proposed_by="agent-core",
                expires_at=T_EXP,
                now=T0,
            )
            self.assertEqual((prop["status"], prop["proposal_version"], prop["duplicate"]), ("pending", 1, False))

            # Duplicate create is idempotent; tampered arguments return 409.
            prop_dup = create_ai_proposal(
                db,
                tenant,
                action_type="crm.opportunity.add_note",
                resource_id=opp["id"],
                arguments={"note": "Cliente solicitó financiamiento a 24 cuotas"},
                idempotency_key="prop-note-1",
                proposed_by="agent-core",
                expires_at=T_EXP,
                now=T0,
            )
            self.assertTrue(prop_dup["duplicate"])
            self.assertEqual(prop_dup["id"], prop["id"])

            with self.assertRaises(HTTPException) as ctx_tamper:
                create_ai_proposal(
                    db,
                    tenant,
                    action_type="crm.opportunity.add_note",
                    resource_id=opp["id"],
                    arguments={"note": "Modificado"},
                    idempotency_key="prop-note-1",
                    proposed_by="agent-core",
                    expires_at=T_EXP,
                    now=T0,
                )
            self.assertEqual(ctx_tamper.exception.status_code, 409)

            # Cannot execute before approval.
            with self.assertRaises(HTTPException) as ctx_unapproved:
                execute_ai_proposal(db, tenant, prop["id"], executor_user_id="reviewer-1", now=T0)
            self.assertEqual(ctx_unapproved.exception.status_code, 409)

            # Approve version 1 -> version 2.
            approved = review_ai_proposal(
                db, tenant, prop["id"], decision="approved", expected_version=1, reviewer_user_id="reviewer-1", review_note="OK", now=T0,
            )
            self.assertEqual((approved["status"], approved["proposal_version"]), ("approved", 2))

            # Execute approved proposal -> applies effect once (version 3).
            executed1 = execute_ai_proposal(db, tenant, prop["id"], executor_user_id="reviewer-1", expected_version=2, now=T0)
            executed2 = execute_ai_proposal(db, tenant, prop["id"], executor_user_id="reviewer-1", expected_version=2, now=T0)
            self.assertFalse(executed1["duplicate"])
            self.assertTrue(executed2["duplicate"])
            self.assertEqual(executed1["effect_result"], executed2["effect_result"])

            # Verify only ONE note activity was created on the opportunity.
            bind_tenant_session(db, tenant.schema_name)
            notes = db.scalars(
                select(OpportunityActivity).where(
                    OpportunityActivity.opportunity_id == opp["id"],
                    OpportunityActivity.activity_type == "note",
                )
            ).all()
            self.assertEqual(len(notes), 1)

    def test_rejection_expiration_and_suspended_tenant_block_execution(self):
        tenant_ok = self._seed_tenant("tenant_fk18_exp", 1702, status="active")
        tenant_susp = self._seed_tenant("tenant_fk18_susp", 1703, status="suspended")

        with Session(self.engine) as db:
            # Expired proposal cannot be approved.
            exp_prop = create_ai_proposal(
                db, tenant_ok, action_type="crm.contact.rename", resource_id=1, arguments={"name": "New Name"},
                idempotency_key="exp-1", proposed_by="agent-core", expires_at=T_EXP, now=T0,
            )
            with self.assertRaises(HTTPException) as ctx_exp:
                review_ai_proposal(
                    db, tenant_ok, exp_prop["id"], decision="approved", expected_version=1, reviewer_user_id="rev-1", now=T_AFTER_EXP,
                )
            self.assertEqual(ctx_exp.exception.status_code, 409)
            self.assertEqual(get_ai_proposal(db, tenant_ok, exp_prop["id"])["status"], "expired")

            # Rejected proposal cannot be executed.
            rej_prop = create_ai_proposal(
                db, tenant_ok, action_type="crm.lead.update_stage", resource_id=1, arguments={"stage": "contactado"},
                idempotency_key="rej-1", proposed_by="agent-core", expires_at=T_EXP, now=T0,
            )
            review_ai_proposal(db, tenant_ok, rej_prop["id"], decision="rejected", expected_version=1, reviewer_user_id="rev-1", now=T0)
            with self.assertRaises(HTTPException) as ctx_rej:
                execute_ai_proposal(db, tenant_ok, rej_prop["id"], executor_user_id="rev-1", now=T0)
            self.assertEqual(ctx_rej.exception.status_code, 409)

            # Suspended tenant blocks execution with 403 even if approved.
            susp_prop = create_ai_proposal(
                db, tenant_susp, action_type="crm.contact.rename", resource_id=1, arguments={"name": "Blocked"},
                idempotency_key="susp-1", proposed_by="agent-core", expires_at=T_EXP, now=T0,
            )
            review_ai_proposal(db, tenant_susp, susp_prop["id"], decision="approved", expected_version=1, reviewer_user_id="rev-1", now=T0)
            with self.assertRaises(HTTPException) as ctx_susp:
                execute_ai_proposal(db, tenant_susp, susp_prop["id"], executor_user_id="rev-1", now=T0)
            self.assertEqual(ctx_susp.exception.status_code, 403)
