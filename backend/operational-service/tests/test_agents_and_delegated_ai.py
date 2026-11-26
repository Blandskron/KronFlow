from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.public_models.tenant_runtime import TenantRuntime
from app.schemas.agent import AgentConfigureRequest, AgentUpdateRequest
from app.schemas.context import (
    AgentRuleCreateIn,
    AgentRulePatchIn,
    AgentTraceCreateIn,
    ContextChunkCreate,
    ContextDocumentCreate,
    ContextDocumentPatch,
)
from app.services.agent_service import (
    configure_agent,
    get_agent,
    list_agent_revisions,
    list_agents,
    publish_agent,
    resolve_runtime_agent,
    rollback_agent,
    update_agent,
)
from app.services.ai_extensions_service import (
    record_ai_usage,
    record_conversation_memory,
    summarize_ai_usage,
)
from app.services.ai_proposal_service import create_ai_proposal, get_ai_proposal
from app.services.context_service import (
    append_setup_message,
    context_status,
    create_agent_rule,
    create_agent_trace,
    create_context_document,
    create_setup_session,
    delete_agent_rule,
    delete_context_document,
    generate_setup_context,
    get_agent_trace,
    get_context_document,
    list_agent_rules,
    list_conversation_memory_by_ref,
    list_conversation_traces,
    patch_agent_rule,
    patch_context_document,
    retrieve_context_sources,
)
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import apply_tenant_schema
from app.tenant_models.operations import Cliente, Conversation
from test_message_identity import PostgresCase


T0 = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


class AgentsAndDelegatedAITests(PostgresCase):
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

    def test_multi_agent_catalog_publish_validation_and_rollback(self):
        tenant = self._seed_tenant("tenant_agents_1", 9101)

        with Session(self.engine) as db:
            doc_active = create_context_document(
                db,
                tenant,
                ContextDocumentCreate(
                    tenant_id="9101",
                    title="Catalogo Pro",
                    filename="catalogo.txt",
                    status="active",
                    raw_text="Plan Pro mensual incluye soporte prioritario y automatizaciones.",
                    chunks=[
                        ContextChunkCreate(
                            chunk_index=0,
                            content="Plan Pro mensual incluye soporte prioritario y automatizaciones.",
                            token_count=9,
                        )
                    ],
                ),
            )
            doc_draft = create_context_document(
                db,
                tenant,
                ContextDocumentCreate(
                    tenant_id="9101",
                    title="Borrador Interno",
                    filename="borrador.txt",
                    status="draft",
                    raw_text="Documento no publicado todavia.",
                    chunks=[ContextChunkCreate(chunk_index=0, content="Documento no publicado todavia.", token_count=4)],
                ),
            )

            agent1 = configure_agent(
                db,
                tenant,
                AgentConfigureRequest(
                    name="Agente Ventas",
                    role="Asesor B2B",
                    tone="warm",
                    language="es",
                    instructions="Responde sobre Plan Pro.",
                    allowed_tools=["handoff_human", "crm.contact.rename"],
                    allowed_document_ids=[doc_active["id"]],
                    is_default=True,
                ),
                now=T0,
            )
            self.assertTrue(agent1["is_default"])
            self.assertEqual(agent1["version"], 1)

            # Second default unsets the first atomically.
            agent2 = configure_agent(
                db,
                tenant,
                AgentConfigureRequest(
                    name="Agente Soporte",
                    role="Mesa tecnica",
                    allowed_tools=["handoff_human"],
                    allowed_document_ids=[doc_draft["id"]],
                    is_default=True,
                ),
                now=T0,
            )
            refetched_1 = get_agent(db, tenant, agent1["id"])
            self.assertFalse(refetched_1["is_default"])
            self.assertTrue(agent2["is_default"])
            self.assertEqual(len(list_agents(db, tenant)), 2)

            # Stale optimistic lock version fails with 409.
            with self.assertRaises(HTTPException) as conflict_err:
                update_agent(
                    db,
                    tenant,
                    agent1["id"],
                    AgentUpdateRequest(name="Stale", expected_version=99),
                    now=T0,
                )
            self.assertEqual(conflict_err.exception.status_code, 409)

            # Publish fails with 422 when pointing to a draft (non-active) document or unknown tool.
            with self.assertRaises(HTTPException) as bad_doc_err:
                publish_agent(db, tenant, agent2["id"], expected_version=agent2["version"], now=T0)
            self.assertEqual(bad_doc_err.exception.status_code, 422)

            with self.assertRaises(HTTPException) as bad_tool_err:
                configure_agent(
                    db,
                    tenant,
                    AgentConfigureRequest(
                        name="BadTool",
                        role="Tester",
                        allowed_tools=["shell.exec"],
                    ),
                    now=T0,
                )
            self.assertEqual(bad_tool_err.exception.status_code, 422)

            # Valid publish creates immutable revision 1 and binds active_revision_id.
            agent1_latest = get_agent(db, tenant, agent1["id"])
            rev1 = publish_agent(
                db,
                tenant,
                agent1["id"],
                expected_version=agent1_latest["version"],
                actor_user_id="user-1",
                note="Inicial",
                now=T0,
            )
            self.assertEqual(rev1["revision_number"], 1)
            self.assertEqual(rev1["status"], "active")

            # Editing draft increments version without overwriting published revision r1.
            updated = update_agent(
                db,
                tenant,
                agent1["id"],
                AgentUpdateRequest(
                    instructions="Instruccion nueva sin publicar.",
                    expected_version=rev1["revision_number"] + 1,
                ),
                now=T0,
            )
            resolved_during_draft = resolve_runtime_agent(db, tenant, agent_id=agent1["id"])
            self.assertEqual(resolved_during_draft["agent_revision_id"], rev1["id"])
            self.assertEqual(resolved_during_draft["instructions"], "Responde sobre Plan Pro.")

            # Publish revision 2, then roll back to revision 1.
            rev2 = publish_agent(
                db,
                tenant,
                agent1["id"],
                expected_version=updated["version"],
                note="V2",
                now=T0,
            )
            self.assertEqual(rev2["revision_number"], 2)

            revisions = list_agent_revisions(db, tenant, agent1["id"])
            self.assertEqual([r["revision_number"] for r in revisions], [2, 1])
            self.assertEqual(revisions[1]["status"], "superseded")

            after_publish_2 = get_agent(db, tenant, agent1["id"])
            rolled_back = rollback_agent(
                db,
                tenant,
                agent1["id"],
                expected_version=after_publish_2["version"],
                revision_id=rev1["id"],
                actor_user_id="user-1",
                now=T0,
            )
            self.assertEqual(rolled_back["active_revision_id"], rev1["id"])
            self.assertEqual(rolled_back["instructions"], "Responde sobre Plan Pro.")

    def test_delegated_context_rules_traces_setup_memory_proposals_and_usage(self):
        tenant = self._seed_tenant("tenant_agents_2", 9102)

        with Session(self.engine) as db:
            # 1. Documents GET/PATCH/DELETE and document_ids RAG filter.
            d1 = create_context_document(
                db,
                tenant,
                ContextDocumentCreate(
                    tenant_id="9102",
                    title="Doc Uno",
                    filename="uno.txt",
                    status="active",
                    raw_text="Precios oficiales Plan Starter y Plan Growth.",
                    chunks=[
                        ContextChunkCreate(chunk_index=0, content="Precios oficiales Plan Starter y Plan Growth.", token_count=7)
                    ],
                ),
            )
            d2 = create_context_document(
                db,
                tenant,
                ContextDocumentCreate(
                    tenant_id="9102",
                    title="Doc Dos",
                    filename="dos.txt",
                    status="active",
                    raw_text="Precios oficiales Plan Enterprise exclusivo VIP.",
                    chunks=[
                        ContextChunkCreate(chunk_index=0, content="Precios oficiales Plan Enterprise exclusivo VIP.", token_count=7)
                    ],
                ),
            )
            self.assertEqual(get_context_document(db, tenant, d1["id"])["title"], "Doc Uno")
            scoped = retrieve_context_sources(db, tenant, "precios oficiales plan", limit=5, document_ids=[d1["id"]])
            self.assertEqual([item["document_id"] for item in scoped], [d1["id"]])

            patched = patch_context_document(db, tenant, d2["id"], ContextDocumentPatch(status="deprecated", title="Doc Dos Obsoleto"))
            self.assertEqual(patched["status"], "deprecated")
            self.assertTrue(context_status(db, tenant)["document_actions"]["delete"])
            delete_context_document(db, tenant, d2["id"])
            with self.assertRaises(HTTPException) as gone_err:
                get_context_document(db, tenant, d2["id"])
            self.assertEqual(gone_err.exception.status_code, 404)

            # 2. Rules CRUD.
            rule = create_agent_rule(
                db,
                tenant,
                AgentRuleCreateIn(name="Sin descuentos manuales", rule_type="guardrail", content="No ofrecer descuentos sin aprobacion.", priority=10),
            )
            self.assertEqual(len(list_agent_rules(db, tenant)), 1)
            rule_upd = patch_agent_rule(db, tenant, rule["id"], AgentRulePatchIn(is_active=False))
            self.assertFalse(rule_upd["is_active"])
            delete_agent_rule(db, tenant, rule["id"])
            self.assertEqual(list_agent_rules(db, tenant), [])

            # 3. Traces & persistent setup-chat generating draft document.
            trace = create_agent_trace(
                db,
                tenant,
                AgentTraceCreateIn(
                    conversation_id="conv-abc",
                    query="Hola precios",
                    output_message="Plan Starter disponible.",
                    confidence=0.91,
                    is_simulation=False,
                    sources=[{"document_id": d1["id"]}],
                    actions=[{"type": "none"}],
                ),
            )
            self.assertEqual(get_agent_trace(db, tenant, trace["id"])["output_message"], "Plan Starter disponible.")
            self.assertEqual(len(list_conversation_traces(db, tenant, "conv-abc")), 1)

            setup = create_setup_session(db, tenant, objective="onboarding")
            setup = append_setup_message(db, tenant, setup["session_id"], content="Vendemos software B2B de cobranza.")
            generated = generate_setup_context(db, tenant, setup["session_id"])
            self.assertIsNotNone(generated["document_id"])
            draft_doc = get_context_document(db, tenant, generated["document_id"])
            self.assertEqual(draft_doc["status"], "draft")

            # 4. Scoped memory lookup by session_id & numeric id + proposal + AI usage simulation flag.
            bind_tenant_session(db, tenant.schema_name)
            db.add_all(
                [
                    Cliente(id=50, rut="rut-50", nombre="Ana", whatsapp_id="56988887777"),
                    Conversation(id=50, session_id="wa-session-50", message={"channel": "whatsapp"}),
                ]
            )
            db.commit()

            record_conversation_memory(
                db,
                tenant,
                50,
                memory_key="plan_interes",
                memory_value="Growth",
                source_type="operator",
                source_ref="op:1",
            )
            by_id = list_conversation_memory_by_ref(db, tenant, "50")
            by_session = list_conversation_memory_by_ref(db, tenant, "wa-session-50")
            self.assertEqual(len(by_id), 1)
            self.assertEqual(by_session[0]["memory_value"], "Growth")

            proposal = create_ai_proposal(
                db,
                tenant,
                action_type="crm.contact.rename",
                resource_id=50,
                arguments={"name": "Ana Maria"},
                idempotency_key="turn-prop-1",
                proposed_by="agent-core",
                rationale="Cliente indico segundo nombre",
                now=T0,
            )
            self.assertEqual(get_ai_proposal(db, tenant, proposal["id"])["status"], "pending")

            record_ai_usage(
                db,
                tenant,
                provider="groq",
                model="llama-3.1-8b-instant",
                prompt_tokens=100,
                completion_tokens=40,
                latency_ms=120,
                estimated_cost_usd=Decimal("0.001000"),
                is_simulation=False,
                pricing_version="2026-11-v1",
                now=T0,
            )
            record_ai_usage(
                db,
                tenant,
                provider="groq",
                model="llama-3.1-8b-instant",
                prompt_tokens=200,
                completion_tokens=80,
                latency_ms=180,
                estimated_cost_usd=Decimal("0.005000"),
                is_simulation=True,
                pricing_version="2026-11-v1",
                now=T0,
            )
            live_only = summarize_ai_usage(db, tenant, include_simulations=False, now=T0)
            with_sim = summarize_ai_usage(db, tenant, include_simulations=True, now=T0)
            self.assertEqual(live_only["requests"], 1)
            self.assertEqual(live_only["total_cost_usd"], "0.001000")
            self.assertEqual(with_sim["requests"], 2)
            self.assertEqual(with_sim["total_cost_usd"], "0.006000")
