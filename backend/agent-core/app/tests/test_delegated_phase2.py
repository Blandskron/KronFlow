from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.v1.routes import agent as agent_route
from app.api.v1.routes import context as context_route
from app.api.v1.routes import rules as rules_route
from app.api.v1.routes import setup as setup_route
from app.api.v1.routes import traces as traces_route
from app.application.orchestration import agent_runtime
from app.core.config import Settings
from app.core.security import CurrentPrincipal, get_current_principal
from app.infrastructure.llm.groq import CompletionObservation, GroqClient
from app.infrastructure.operational_context import OperationalContextSource, operational_context_client
from app.main import app


def _manager_principal():
    return CurrentPrincipal(
        "10",
        "1",
        ["MANAGER"],
        ["agents.create", "audit.read"],
        {"token_type": "access"},
    )


def _op_settings():
    return Settings(
        _env_file=None,
        persistence_mode="operational",
        allow_insecure_tenant_header=True,
        internal_token="synthetic-internal",
        chat_provider="groq",
        groq_api_key=SecretStr("synthetic-groq"),
        groq_model="llama-3.1-8b-instant",
    )


def _turn_payload(raw_payload=None):
    return {
        "tenant_id": "1",
        "channel": "whatsapp",
        "conversation_id": "conv-wa-100",
        "customer": {"external_id": "56911112222", "name": "Carla"},
        "message": {"type": "text", "content": "Cual es el precio del plan pro?", "attachments": []},
        "metadata": {"raw_payload": raw_payload or {}},
    }


def test_delegated_documents_rules_traces_and_setup_chat(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_current_principal, _manager_principal)
    for mod in (context_route, rules_route, traces_route, setup_route):
        monkeypatch.setattr(mod, "get_settings", _op_settings)

    deleted_docs = []
    monkeypatch.setattr(
        operational_context_client,
        "get_document",
        lambda tenant_id, doc_id: {
            "id": doc_id,
            "tenant_id": tenant_id,
            "title": "Guia comercial",
            "filename": "guia.txt",
            "content_type": "text/plain",
            "status": "active",
            "priority": 100,
            "version": 1,
        },
    )
    monkeypatch.setattr(
        operational_context_client,
        "patch_document",
        lambda tenant_id, doc_id, payload: {
            "id": doc_id,
            "tenant_id": tenant_id,
            "title": payload.get("title", "Guia comercial"),
            "filename": "guia.txt",
            "status": payload.get("status", "active"),
            "priority": 100,
            "version": 1,
        },
    )
    monkeypatch.setattr(
        operational_context_client,
        "delete_document",
        lambda tenant_id, doc_id: deleted_docs.append((tenant_id, doc_id)),
    )

    monkeypatch.setattr(
        operational_context_client,
        "list_rules",
        lambda tenant_id: [
            {"id": 3, "tenant_id": tenant_id, "name": "Tono", "rule_type": "style", "content": "Breve", "priority": 10, "is_active": True}
        ],
    )
    monkeypatch.setattr(
        operational_context_client,
        "create_rule",
        lambda tenant_id, payload: {"id": 4, "tenant_id": tenant_id, **payload},
    )
    monkeypatch.setattr(
        operational_context_client,
        "patch_rule",
        lambda tenant_id, rule_id, payload: {
            "id": rule_id,
            "tenant_id": tenant_id,
            "name": "Tono",
            "rule_type": "style",
            "content": payload.get("content", "Claro"),
            "priority": 10,
            "is_active": True,
        },
    )
    monkeypatch.setattr(operational_context_client, "delete_rule", lambda tenant_id, rule_id: None)
    monkeypatch.setattr(
        operational_context_client,
        "get_trace",
        lambda tenant_id, trace_id: {"id": trace_id, "conversation_id": "conv-1", "confidence": 0.9, "sources": []},
    )
    monkeypatch.setattr(
        operational_context_client,
        "list_conversation_traces",
        lambda tenant_id, conv_id: [{"id": 9, "conversation_id": conv_id, "query": "hola"}],
    )
    monkeypatch.setattr(
        operational_context_client,
        "create_setup_session",
        lambda tenant_id, payload: {"session_id": "sess-99", "next_question": "Cuentanos de tu empresa"},
    )
    monkeypatch.setattr(
        operational_context_client,
        "send_setup_message",
        lambda tenant_id, session_id, payload: {"session_id": session_id, "next_question": "Que tono prefieres?"},
    )
    monkeypatch.setattr(
        operational_context_client,
        "generate_setup_context",
        lambda tenant_id, session_id: {"summary": "Resumen generado", "document_id": 55},
    )

    client = TestClient(app)
    assert client.get("/api/v1/context/documents/7").json()["data"]["title"] == "Guia comercial"
    assert client.patch("/api/v1/context/documents/7", json={"title": "Guia v2"}).json()["data"]["title"] == "Guia v2"
    assert client.delete("/api/v1/context/documents/7").status_code == 204
    assert deleted_docs == [("1", 7)]

    assert client.get("/api/v1/agent/rules").json()["data"][0]["id"] == 3
    assert client.post("/api/v1/agent/rules", json={"name": "R2", "rule_type": "general", "content": "Texto"}).status_code == 201
    assert client.patch("/api/v1/agent/rules/3", json={"content": "Actualizado"}).json()["data"]["content"] == "Actualizado"
    assert client.delete("/api/v1/agent/rules/3").status_code == 204

    assert client.get("/api/v1/agent/traces/9").json()["data"]["id"] == 9
    assert client.get("/api/v1/agent/conversations/conv-1/traces").json()["data"][0]["id"] == 9

    s = client.post("/api/v1/setup-chat/sessions", json={}).json()["data"]
    assert s["session_id"] == "sess-99"
    assert client.post("/api/v1/setup-chat/sessions/sess-99/messages", json={"content": "B2B"}).json()["data"]["session_id"] == "sess-99"
    assert client.post("/api/v1/setup-chat/sessions/sess-99/generate-context").json()["data"]["document_id"] == 55


def test_runtime_live_vs_simulation_resolves_agent_memory_proposals_and_usage(monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_current_principal, _manager_principal)
    monkeypatch.setattr(agent_route, "get_settings", _op_settings)
    monkeypatch.setattr(agent_runtime, "get_settings", _op_settings)

    captured_prompts = []
    retrieve_calls = []
    proposals_created = []
    usage_records = []
    trace_records = []

    monkeypatch.setattr(
        operational_context_client,
        "resolve_active_agent",
        lambda tenant_id, agent_id=None, agent_revision_id=None: {
            "agent_id": 12,
            "agent_revision_id": 34,
            "revision_number": 3,
            "name": "Sofi Ventas",
            "role": "Asesora B2B",
            "tone": "friendly",
            "language": "es",
            "instructions": "Responde solo usando los documentos autorizados.",
            "allowed_tools": ["crm.contact.rename", "handoff_human"],
            "allowed_document_ids": [7, 8],
        },
    )
    monkeypatch.setattr(
        operational_context_client,
        "list_conversation_memory",
        lambda tenant_id, conv_id, limit=10: [
            {"memory_key": "empresa", "memory_value": "ACME Ltda"}
        ],
    )

    def _fake_retrieve(tenant_id, query, limit=3, document_ids=None):
        retrieve_calls.append({"tenant_id": tenant_id, "document_ids": document_ids})
        return [
            OperationalContextSource(
                document_id=7,
                chunk_id=1,
                title="Precios",
                score=0.95,
                content="El plan Pro cuesta $99 USD mensuales.",
            )
        ]

    monkeypatch.setattr(operational_context_client, "retrieve_sources", _fake_retrieve)
    monkeypatch.setattr(operational_context_client, "create_proposal", lambda tenant_id, payload: proposals_created.append(payload) or {"id": 1})
    monkeypatch.setattr(operational_context_client, "record_ai_usage", lambda tenant_id, **kwargs: usage_records.append(kwargs) or {"id": 1})
    monkeypatch.setattr(operational_context_client, "record_trace", lambda tenant_id, payload: trace_records.append(payload) or {"id": 1})

    def _fake_complete(self, messages):
        captured_prompts.append(messages)
        self.last_observation = CompletionObservation(
            provider="groq",
            model="llama-3.1-8b-instant",
            prompt_tokens=150,
            completion_tokens=45,
            latency_ms=110,
        )
        return "El plan Pro tiene un valor de $99 USD mensuales."

    monkeypatch.setattr(GroqClient, "complete", _fake_complete)

    client = TestClient(app)
    proposed_action = {"type": "crm.contact.rename", "resource_id": 50, "arguments": {"name": "Carla Diaz"}}

    live_res = client.post("/api/v1/agent/messages", json=_turn_payload({"proposed_action": proposed_action}))
    assert live_res.status_code == 200
    live_data = live_res.json()["data"]
    assert live_data["agent_id"] == 12
    assert live_data["agent_revision_id"] == 34
    assert retrieve_calls[-1]["document_ids"] == [7, 8]
    assert "ACME Ltda" in captured_prompts[-1][0].content
    assert len(proposals_created) == 1
    assert proposals_created[0]["action_type"] == "crm.contact.rename"
    assert usage_records[-1]["is_simulation"] is False
    assert usage_records[-1]["agent_revision_id"] == 34
    assert usage_records[-1]["pricing_version"] == "2026-11-v1"
    assert trace_records[-1]["is_simulation"] is False

    # Simulate must NOT create persistent CRM proposals, and marks usage + trace as is_simulation=True.
    sim_res = client.post("/api/v1/agent/simulate", json=_turn_payload({"proposed_action": proposed_action}))
    assert sim_res.status_code == 200
    assert len(proposals_created) == 1
    assert usage_records[-1]["is_simulation"] is True
    assert trace_records[-1]["is_simulation"] is True
