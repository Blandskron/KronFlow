import json
import logging

import httpx
import pytest
from fastapi import status
from pydantic import SecretStr, ValidationError

from app.api.v1.schemas.agent import AgentMessageRequest
from app.application.orchestration import agent_runtime
from app.application.orchestration.chat_prompt import build_context_prompt
from app.core.config import Settings
from app.domain.ports.llm import ChatInputBudgetExceeded, ChatMessage
from app.infrastructure.llm.groq import GroqClient
from app.infrastructure.operational_context import OperationalContextSource


def test_chat_uses_groq_when_a_key_is_set_unless_explicitly_local():
    settings = Settings(
        _env_file=None,
        chat_provider="auto",
        groq_api_key=SecretStr(""),
    )
    assert not GroqClient(settings).enabled_for_chat

    settings.groq_api_key = SecretStr("synthetic-groq")
    assert GroqClient(settings).enabled_for_chat
    settings.chat_provider = "local"
    assert not GroqClient(settings).enabled_for_chat


def test_groq_uses_bearer_and_configured_model(monkeypatch):
    def completion(request):
        assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer synthetic-groq"
        assert json.loads(request.content) == {
            "model": "openai/gpt-oss-20b",
            "messages": [{"role": "user", "content": "Hola"}],
            "temperature": 0.3,
            "max_completion_tokens": 2000,
        }
        return httpx.Response(200, json={"choices": [{"message": {"content": " Hola. "}}]})

    client = httpx.Client(transport=httpx.MockTransport(completion))
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: client)
    settings = Settings(
        _env_file=None, chat_provider="groq", groq_api_key=SecretStr("synthetic-groq")
    )
    assert GroqClient(settings).complete([ChatMessage(role="user", content="Hola")]) == "Hola."


def test_operational_mode_requests_human_when_groq_fails(monkeypatch):
    def rate_limited(_request):
        return httpx.Response(status.HTTP_429_TOO_MANY_REQUESTS)

    client = httpx.Client(transport=httpx.MockTransport(rate_limited))
    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key=SecretStr("synthetic-groq"))
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_runtime,
        "_safe_load_ai_policy",
        lambda _tenant_id: {"ai_enabled": True, "allow_external_ai_transfer": True, "memory_auto_capture": False},
    )
    monkeypatch.setattr(
        agent_runtime.operational_context_client,
        "retrieve_sources",
        lambda *_args: [OperationalContextSource(1, 1, "Fixture", 0.8, "Abre a las nueve.")],
    )
    request = AgentMessageRequest(
        channel="whatsapp",
        conversation_id="synthetic-conversation",
        customer={"external_id": "synthetic-customer"},
        message={"content": "¿Cuál es el horario?"},
    )
    response = agent_runtime.process_stateless_agent_message("tenant-a", request)
    assert response.requires_human
    assert response.next_step == "handoff"
    assert response.actions[0].type == "handoff_human"
    assert response.sources


def test_simple_whatsapp_turns_work_without_documents(monkeypatch):
    def unexpected_retrieval(*_args):
        raise AssertionError("A greeting, thanks or explicit handoff does not need business documents.")

    monkeypatch.setattr(agent_runtime, "get_settings", lambda: Settings(_env_file=None, chat_provider="local"))
    monkeypatch.setattr(agent_runtime.operational_context_client, "retrieve_sources", unexpected_retrieval)
    for message, expected_handoff in [("¡Hola!", False), ("Gracias", False), ("Quiero hablar con una persona", True)]:
        request = AgentMessageRequest(
            channel="whatsapp", conversation_id="synthetic", customer={"external_id": "synthetic"},
            message={"content": message},
        )
        response = agent_runtime.process_stateless_agent_message("tenant-a", request)
        assert response.requires_human is expected_handoff


@pytest.mark.parametrize("overrides", [
    {"chat_input_max_chars": 0}, {"chat_completion_max_tokens": 0}, {"low_confidence_threshold": 1.01},
])
def test_invalid_budget_settings_are_rejected(overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_context_budget_keeps_complete_excerpts_and_the_question():
    system = "Usa las fuentes"
    question = "¿Qué dice?"
    first = "Frase completa uno."
    second = "Frase completa dos."
    exact = len(system) + len(f"Contexto:\n{first}\n\nPregunta:\n{question}")
    messages, sources_used = build_context_prompt(system, question, [first, second], exact)
    assert sources_used == 1
    assert messages == [ChatMessage("system", system), ChatMessage("user", f"Contexto:\n{first}\n\nPregunta:\n{question}")]
    with pytest.raises(ChatInputBudgetExceeded):
        build_context_prompt(system, question, [first], exact - 1)


def test_groq_rejects_input_over_budget_before_opening_http(monkeypatch, caplog):
    def no_http(**_kwargs):
        pytest.fail("Provider HTTP must not be initialized when over budget")

    monkeypatch.setattr(httpx, "Client", no_http)
    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key="synthetic", chat_input_max_chars=2)
    with caplog.at_level(logging.INFO, logger="app.infrastructure.llm.groq"), pytest.raises(ChatInputBudgetExceeded):
        GroqClient(settings).complete([ChatMessage("system", "😀"), ChatMessage("user", "áé")])
    assert "outcome=input_budget_exceeded" in caplog.text
    assert "input_chars=3" in caplog.text
    assert "áé" not in caplog.text


@pytest.mark.parametrize(("usage", "expected"), [
    ({"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 11}, "input_tokens=7 output_tokens=4 total_tokens=11"),
    ({"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}, "input_tokens=0 output_tokens=0 total_tokens=0"),
    (None, "input_tokens=None output_tokens=None total_tokens=None"),
    ({"prompt_tokens": True, "completion_tokens": 4, "total_tokens": 5}, "input_tokens=None output_tokens=None total_tokens=None"),
    ({"prompt_tokens": 7, "completion_tokens": 4, "total_tokens": 99}, "input_tokens=None output_tokens=None total_tokens=None"),
])
def test_groq_observes_only_valid_token_counts(monkeypatch, caplog, usage, expected):
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json={
        "choices": [{"message": {"content": "synthetic_reply_value"}}], "usage": usage,
    }))
    client = httpx.Client(transport=transport)
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: client)
    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key="synthetic_key_value", chat_input_max_chars=22)
    with caplog.at_level(logging.INFO, logger="app.infrastructure.llm.groq"):
        assert GroqClient(settings).complete([ChatMessage("user", "synthetic_prompt_value")]) == "synthetic_reply_value"
    assert "outcome=completed elapsed_ms=" in caplog.text
    assert expected in caplog.text
    assert "synthetic_" not in caplog.text


def test_successful_reply_identifies_only_excerpts_sent_to_the_provider(monkeypatch):
    sources = [
        OperationalContextSource(1, 1, "Used", 0.9, "Abre a las nueve."),
        OperationalContextSource(2, 2, "Over budget", 0.8, "Horario adicional." * 40),
    ]
    request = AgentMessageRequest(channel="whatsapp", conversation_id="synthetic", customer={"external_id": "synthetic"},
                                  message={"content": "¿Cuál es el horario?"})
    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key="synthetic", chat_input_max_chars=400)
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_runtime,
        "_safe_load_ai_policy",
        lambda _tenant_id: {"ai_enabled": True, "allow_external_ai_transfer": True, "memory_auto_capture": False},
    )
    monkeypatch.setattr(agent_runtime.operational_context_client, "retrieve_sources", lambda *_args: sources)

    def complete(_client, messages):
        assert sources[0].content in messages[1].content
        assert sources[1].content not in messages[1].content
        return sources[0].content

    monkeypatch.setattr(GroqClient, "complete", complete)
    response = agent_runtime.process_stateless_agent_message("tenant-a", request)
    assert not response.requires_human
    assert [source.source_id for source in response.sources] == ["context-document:1:chunk:1"]
