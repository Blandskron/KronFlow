import json
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.v1.schemas.agent import AgentMessageRequest, AgentMessageResponse
from app.application.orchestration import agent_runtime
from app.core.config import Settings
from app.core.database import Base
from app.infrastructure.operational_context import OperationalContextSource
from app.models.context import BusinessContextDocument, DocumentChunk
from app.models.conversation import ConversationSession


DATASET = json.loads((Path(__file__).parent / "fixtures" / "agent_evaluation.v1.json").read_text(encoding="utf-8"))


def message(case_id: str, question: str) -> AgentMessageRequest:
    return AgentMessageRequest(
        channel="webchat", conversation_id=case_id, customer={"external_id": "synthetic"}, message={"content": question},
    )


@pytest.mark.parametrize("case", DATASET["cases"], ids=lambda case: case["id"])
def test_versioned_agent_evaluation(case, monkeypatch):
    assert DATASET["version"] == 1
    tenant = case["tenant"]
    source_text = DATASET["source_text"][tenant]
    retrieval = case.get("retrieval", "normal")
    provider = case.get("provider", "local")
    settings = Settings(_env_file=None, chat_provider="local" if provider == "local" else "groq",
                        groq_api_key="synthetic", chat_input_max_chars=case.get("budget", 12000))
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    if provider != "local":
        monkeypatch.setattr(
            agent_runtime,
            "_safe_load_ai_policy",
            lambda _tenant_id: {"ai_enabled": True, "allow_external_ai_transfer": True, "memory_auto_capture": False},
        )

    def retrieve(authenticated_tenant, question):
        assert retrieval != "skip"
        assert authenticated_tenant == tenant
        assert question == case["question"]
        if retrieval == "unavailable":
            raise HTTPException(503, "Synthetic outage")
        if retrieval == "invalid":
            raise ValueError("Synthetic malformed response")
        if retrieval == "empty":
            return []
        score = {"weak": 0.1, "threshold": settings.low_confidence_threshold}.get(retrieval, 0.8)
        return [OperationalContextSource(1, 1, "Business hours", score, source_text)]

    def complete(request):
        assert provider not in ("local", "must_not_call")
        body = json.loads(request.content)
        assert source_text in body["messages"][1]["content"]
        assert body["messages"][1]["content"].endswith(case["question"])
        if provider == "success":
            return httpx.Response(200, json={"choices": [{"message": {"content": source_text}}]})
        if provider == "rate_limited":
            return httpx.Response(429)
        if provider == "timeout":
            raise httpx.ReadTimeout("Synthetic timeout")
        assert provider == "invalid"
        return httpx.Response(200, json={"choices": []})

    client = httpx.Client(transport=httpx.MockTransport(complete))
    monkeypatch.setattr(agent_runtime.operational_context_client, "retrieve_sources", retrieve)
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: client)
    request = message(case["id"], case["question"])
    result = agent_runtime.process_stateless_agent_message(tenant, request)
    assert AgentMessageResponse.model_validate_json(result.model_dump_json()) == result
    assert (result.tenant_id, result.conversation_id) == (tenant, case["id"])
    assert 0 <= result.confidence <= 1
    assert result.reply.type == "text" and result.reply.content
    reason = case.get("reason")
    assert result.requires_human is bool(reason)
    assert result.next_step == ("handoff" if reason else "continue_conversation")
    assert len(result.actions) == 1
    assert result.actions[0].type == ("handoff_human" if reason else "none")
    assert result.actions[0].payload.get("reason") == reason
    if "expect_text" in case:
        assert case["expect_text"] in result.reply.content
    if "source_count" in case:
        assert len(result.sources) == case["source_count"]
        assert result.sources[0].source_id == "context-document:1:chunk:1"


def test_retrieval_denial_remains_an_error(monkeypatch):
    def denied(*_args):
        raise HTTPException(403, "Workspace is not active")

    monkeypatch.setattr(agent_runtime.operational_context_client, "retrieve_sources", denied)
    with pytest.raises(HTTPException) as error:
        agent_runtime.process_stateless_agent_message("tenant-a", message("blocked", "¿Cuál es el horario?"))
    assert error.value.status_code == 403


@pytest.mark.parametrize("fields", [{"score": "NaN"}, {"score": 1.1}, {"content": " "}, {"content": None}])
def test_malformed_operational_sources_are_never_used_for_a_reply(monkeypatch, fields):
    source = {"document_id": 1, "chunk_id": 1, "title": "Synthetic", "score": 0.9, "content": "Unverified snippet"}
    client = agent_runtime.operational_context_client
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: [source | fields])
    response = agent_runtime.process_stateless_agent_message("tenant-a", message("invalid", "¿Cuál es el horario?"))
    assert response.requires_human
    assert response.actions[0].payload["reason"] == "context_unavailable"
    assert not response.sources


def test_persistent_runtime_records_the_same_handoff_and_keeps_retrieval_tenant_scoped(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(_env_file=None, chat_provider="local", low_confidence_threshold=0.5)
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    with Session(engine) as db:
        document = BusinessContextDocument(tenant_id="tenant-a", title="Business hours", filename="schedule.txt", status="active")
        document.chunks = [DocumentChunk(tenant_id="tenant-a", chunk_index=0, content=DATASET["source_text"]["tenant-a"])]
        db.add(document)
        db.commit()
        query = message("shared-key", "horario atención")
        allowed = agent_runtime.process_agent_message(db, "tenant-a", query)
        hidden = agent_runtime.process_agent_message(db, "tenant-b", query)
        assert "abre a las nueve" in allowed.reply.content
        assert allowed.sources and not hidden.sources
        assert hidden.requires_human and hidden.actions[0].payload["reason"] == "insufficient_context"
        weak = agent_runtime.process_agent_message(db, "tenant-a", message("shared-key", "horario exportación marítima"))
        assert weak.sources and weak.confidence < 0.5
        assert weak.requires_human and weak.next_step == "handoff"
        assert weak.actions[0].payload["reason"] == "insufficient_context"
        sessions = db.scalars(select(ConversationSession).order_by(ConversationSession.tenant_id)).all()
        assert [(session.tenant_id, session.requires_human) for session in sessions] == [("tenant-a", True), ("tenant-b", True)]
