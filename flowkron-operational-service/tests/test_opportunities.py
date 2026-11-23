from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.system_event import SystemEvent
from app.services.opportunity_service import (
    add_opportunity_activity,
    create_opportunity,
    create_pipeline_stage,
    get_opportunity,
    list_opportunities,
    list_pipeline_stages,
    update_opportunity,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.operations import Cliente, Conversation, Lead
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 23, 13, 0, tzinfo=timezone.utc)


class OpportunityPipelineTests(PostgresCase):
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
                Cliente(id=1, rut=f"rut-{auth_id}", nombre=f"Contact {auth_id}", whatsapp_id=f"56900000{auth_id}"),
                Conversation(id=1, session_id=f"56900000{auth_id}", message={"channel": "whatsapp"}),
            ])
            db.flush()
            db.add(Lead(id=1, cliente_id=1))
            db.commit()
        return tenant

    def test_lead_to_opportunity_stage_transitions_versioning_and_close_won(self):
        tenant = self._seed_tenant("tenant_fk29_flow", 2901)

        with Session(self.engine) as db:
            stages = list_pipeline_stages(db, tenant)
            stage_by_slug = {s["slug"]: s for s in stages}
            self.assertEqual([s["slug"] for s in stages], ["qualification", "proposal", "negotiation", "won", "lost"])

            # Create from lead_id without explicit contact_id -> resolves contact_id=1 automatically.
            created = create_opportunity(
                db,
                tenant,
                title="Flota SUV 2026",
                lead_id=1,
                conversation_id=1,
                owner_user_id="seller-1",
                amount=Decimal("24500.50"),
                currency="usd",
                actor_user_id="seller-1",
                now=T0,
            )
            self.assertEqual(created["contact_id"], 1)
            self.assertEqual(created["stage_slug"], "qualification")
            self.assertEqual(created["currency"], "USD")
            self.assertEqual(created["version"], 1)
            self.assertEqual(created["outcome"], "open")

            # Stale version must fail with 409 Conflict.
            with self.assertRaises(HTTPException) as ctx:
                update_opportunity(
                    db, tenant, created["id"], expected_version=99, stage_id=stage_by_slug["proposal"]["id"], actor_user_id="seller-1",
                )
            self.assertEqual(ctx.exception.status_code, 409)

            # Move to proposal (v1 -> v2) and add commercial note.
            moved = update_opportunity(
                db,
                tenant,
                created["id"],
                expected_version=1,
                stage_id=stage_by_slug["proposal"]["id"],
                owner_user_id="seller-2",
                actor_user_id="seller-1",
                note="Cotización enviada",
                now=T0,
            )
            self.assertEqual((moved["stage_slug"], moved["owner_user_id"], moved["version"]), ("proposal", "seller-2", 2))

            note_act = add_opportunity_activity(db, tenant, created["id"], actor_user_id="seller-2", note="Cliente confirmó reunión", now=T0)
            self.assertEqual(note_act["activity_type"], "note")

            # Close as won (v2 -> v3) -> automatically aligns stage to won & records closed_at + audit event.
            won = update_opportunity(
                db,
                tenant,
                created["id"],
                expected_version=2,
                outcome="won",
                close_reason="Firma de contrato",
                actor_user_id="seller-2",
                now=T0,
            )
            self.assertEqual((won["outcome"], won["stage_slug"], won["version"]), ("won", "won", 3))
            self.assertIsNotNone(won["closed_at"])
            self.assertEqual(
                [a["activity_type"] for a in won["activities"]],
                ["created", "stage_changed", "owner_changed", "note", "stage_changed", "closed_won"],
            )

            # Verify SystemEvents emitted atomically for this tenant.
            events = db.scalars(
                select(SystemEvent.event_type)
                .where(SystemEvent.auth_tenant_id == tenant.auth_tenant_id)
                .order_by(SystemEvent.id.asc())
            ).all()
            self.assertEqual(events, ["opportunity.created", "opportunity.stage.changed", "opportunity.stage.changed", "opportunity.won"])

    def test_lost_requires_close_reason_and_custom_stage_filtering(self):
        tenant = self._seed_tenant("tenant_fk29_lost", 2902)

        with Session(self.engine) as db:
            custom = create_pipeline_stage(db, tenant, slug="legal_review", name="Revisión Legal", position=25, stage_kind="open")
            opp = create_opportunity(
                db, tenant, title="Contrato anual", contact_id=1, stage_id=custom["id"], owner_user_id="rep-a", actor_user_id="rep-a", now=T0,
            )
            # Closing as lost without close_reason fails with 422.
            with self.assertRaises(HTTPException) as ctx:
                update_opportunity(db, tenant, opp["id"], expected_version=1, outcome="lost", actor_user_id="rep-a", now=T0)
            self.assertEqual(ctx.exception.status_code, 422)

            lost = update_opportunity(
                db, tenant, opp["id"], expected_version=1, outcome="lost", close_reason="Presupuesto pospuesto", actor_user_id="rep-a", now=T0,
            )
            self.assertEqual((lost["outcome"], lost["stage_slug"], lost["close_reason"]), ("lost", "lost", "Presupuesto pospuesto"))

            items, total = list_opportunities(db, tenant, outcome="lost", owner_user_id="rep-a")
            self.assertEqual(total, 1)
            self.assertEqual(items[0]["id"], opp["id"])

    def test_two_tenants_with_same_opportunity_id_are_strictly_isolated(self):
        tenant_a = self._seed_tenant("tenant_fk29_iso_a", 2903)
        tenant_b = self._seed_tenant("tenant_fk29_iso_b", 2904)

        with Session(self.engine) as db:
            opp_a = create_opportunity(db, tenant_a, title="Deal A", contact_id=1, owner_user_id="a1", actor_user_id="a1", now=T0)
            self.assertEqual(opp_a["id"], 1)

            # Tenant B cannot read or mutate opportunity 1 (does not exist in tenant B schema).
            with self.assertRaises(HTTPException) as ctx_get:
                get_opportunity(db, tenant_b, 1)
            self.assertEqual(ctx_get.exception.status_code, 404)

            with self.assertRaises(HTTPException) as ctx_upd:
                update_opportunity(db, tenant_b, 1, expected_version=1, title="Hijack", actor_user_id="b1", now=T0)
            self.assertEqual(ctx_upd.exception.status_code, 404)

            # Tenant B creates its own independent opportunity with id=1.
            opp_b = create_opportunity(db, tenant_b, title="Deal B", contact_id=1, owner_user_id="b1", actor_user_id="b1", now=T0)
            self.assertEqual(opp_b["id"], 1)
            self.assertEqual(get_opportunity(db, tenant_a, 1)["title"], "Deal A")
            self.assertEqual(get_opportunity(db, tenant_b, 1)["title"], "Deal B")
