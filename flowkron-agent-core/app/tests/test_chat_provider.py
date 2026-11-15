import json

import httpx
from fastapi import status
from pydantic import SecretStr

from app.api.v1.schemas.agent import AgentMessageRequest
from app.application.orchestration import agent_runtime
from app.core.config import Settings
from app.domain.ports.llm import ChatMessage
from app.infrastructure.llm.azure_openai import AzureOpenAIClient
from app.infrastructure.llm.chat_provider import chat_client
from app.infrastructure.llm.groq import GroqClient
from app.infrastructure.operational_context import OperationalContextSource


def test_provider_selection_preserves_azure_and_local():
    settings = Settings(
        _env_file=None,
        chat_provider="auto",
        groq_api_key=SecretStr(""),
        azure_openai_enabled=True,
        azure_openai_api_key="synthetic-azure",
        chat_completion_url="https://example.com/completions",
    )
    assert isinstance(chat_client(settings), AzureOpenAIClient)
    assert chat_client(settings).enabled_for_chat

    settings.groq_api_key = SecretStr("synthetic-groq")
    assert isinstance(chat_client(settings), GroqClient)
    settings.chat_provider = "azure"
    assert isinstance(chat_client(settings), AzureOpenAIClient)
    settings.chat_provider = "local"
    assert chat_client(settings) is None


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
    settings = Settings(_env_file=None, groq_api_key=SecretStr("synthetic-groq"))
    assert GroqClient(settings).complete([ChatMessage(role="user", content="Hola")]) == "Hola."


def test_operational_mode_requests_human_when_groq_fails(monkeypatch):
    def rate_limited(_request):
        return httpx.Response(status.HTTP_429_TOO_MANY_REQUESTS)

    client = httpx.Client(transport=httpx.MockTransport(rate_limited))
    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key=SecretStr("synthetic-groq"))
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
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
