"""PRV-004 & PRV-005 / QG-1: Privacy-by-Default external AI gate and pre-egress PII scrubber tests."""

import json
import logging

import httpx
from pydantic import SecretStr

from app.api.v1.schemas.agent import AgentMessageRequest
from app.application.orchestration import agent_runtime
from app.core.config import Settings
from app.domain.ports.llm import ChatMessage
from app.infrastructure.llm.groq import GroqClient
from app.infrastructure.llm.pii_scrubber import (
    ScrubSession,
    is_valid_chilean_rut,
    is_valid_luhn_pan,
    scrub_text,
)
from app.infrastructure.operational_context import OperationalContextSource


def test_pii_scrubber_redacts_chilean_rut_email_phone_and_luhn_card():
    assert is_valid_chilean_rut("12.345.678-5")
    assert is_valid_chilean_rut("12345678-5")
    assert not is_valid_chilean_rut("12.345.678-9")

    # Standard synthetic Luhn-valid test card (4111...)
    test_pan = "4111-1111-1111-1111"
    assert is_valid_luhn_pan(test_pan)
    assert not is_valid_luhn_pan("4111-1111-1111-1112")

    raw = (
        "Hola, soy Ana. Mi RUT es 12.345.678-5, correo ana.perez@example.test, "
        "teléfono +56 9 8765 4321 y tarjeta 4111-1111-1111-1111. Pedido #202611."
    )
    scrubbed, session = scrub_text(raw)
    assert "12.345.678-5" not in scrubbed
    assert "ana.perez@example.test" not in scrubbed
    assert "+56 9 8765 4321" not in scrubbed
    assert test_pan not in scrubbed
    assert "[RUT_1]" in scrubbed
    assert "[EMAIL_1]" in scrubbed
    assert "[PHONE_1]" in scrubbed
    assert "[CARD_1]" in scrubbed
    # Non-PII order reference stays intact.
    assert "Pedido #202611" in scrubbed
    # Reversible restoration in local memory works identically.
    assert session.restore_text(scrubbed) == raw


def test_groq_client_never_sends_raw_pii_over_http(monkeypatch):
    captured_payload: dict = {}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "Recibido."}}]})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))
    monkeypatch.setattr(httpx, "Client", lambda **_kwargs: client)

    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key=SecretStr("synthetic-key"))
    reply = GroqClient(settings).complete(
        [
            ChatMessage(role="system", content="Contexto del cliente 12.345.678-5"),
            ChatMessage(
                role="user",
                content="Escríbeme a cliente@example.test o llama al +56987654321, tarjeta 4111 1111 1111 1111",
            ),
        ]
    )
    assert reply == "Recibido."
    serialized = json.dumps(captured_payload)
    for forbidden in ("12.345.678-5", "cliente@example.test", "+56987654321", "4111 1111 1111 1111"):
        assert forbidden not in serialized
    assert "[RUT_1]" in serialized
    assert "[EMAIL_1]" in serialized
    assert "[PHONE_1]" in serialized
    assert "[CARD_1]" in serialized


def test_external_ai_transfer_is_blocked_by_default_and_operates_locally(monkeypatch, caplog):
    def fail_if_http_called(**_kwargs):
        raise AssertionError("Groq HTTP must NOT be called when allow_external_ai_transfer is False")

    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key=SecretStr("synthetic-key"))
    monkeypatch.setattr(httpx, "Client", fail_if_http_called)
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_runtime.operational_context_client,
        "retrieve_sources",
        lambda *_args: [OperationalContextSource(1, 1, "Horario", 0.9, "Atendemos de 9 a 18 horas.")],
    )

    request = AgentMessageRequest(
        channel="whatsapp",
        conversation_id="conv-prv004-1",
        customer={"external_id": "cust-1"},
        message={"content": "¿Cuál es el horario de atención?"},
    )
    with caplog.at_level(logging.INFO, logger="app.application.orchestration.agent_runtime"):
        response = agent_runtime.process_stateless_agent_message("tenant-prv", request)

    assert not response.requires_human
    assert "Atendemos de 9 a 18 horas." in response.reply.content
    assert "external_ai_egress outcome=blocked_by_policy" in caplog.text


def test_memory_auto_capture_is_disabled_by_default(monkeypatch):
    called_memory = False

    def spy_memory(*_args, **_kwargs):
        nonlocal called_memory
        called_memory = True
        return [{"memory_key": "secret", "memory_value": "value"}]

    settings = Settings(_env_file=None, chat_provider="local", internal_token="synthetic-internal")
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(
        agent_runtime.operational_context_client,
        "get_tenant_ai_policy",
        lambda _tid: {"ai_enabled": True, "allow_external_ai_transfer": False, "memory_auto_capture": False},
    )
    monkeypatch.setattr(agent_runtime.operational_context_client, "list_conversation_memory", spy_memory)
    monkeypatch.setattr(
        agent_runtime.operational_context_client,
        "retrieve_sources",
        lambda *_args: [OperationalContextSource(1, 1, "Doc", 0.9, "Respuesta local.")],
    )

    request = AgentMessageRequest(
        channel="whatsapp",
        conversation_id="conv-prv004-2",
        customer={"external_id": "cust-2"},
        message={"content": "¿Cómo funciona?"},
    )
    response = agent_runtime.process_stateless_agent_message("tenant-prv", request)
    assert not called_memory
    assert "Respuesta local." in response.reply.content


def test_scrub_session_consistent_placeholders():
    session = ScrubSession()
    first = session.scrub_text("Email: a@b.cl y de nuevo a@b.cl")
    assert first == "Email: [EMAIL_1] y de nuevo [EMAIL_1]"
    assert session.redaction_count == 1


def test_prv012_greeting_and_response_include_eu_ai_act_art50_disclosure(monkeypatch):
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: Settings(_env_file=None, chat_provider="local"))
    request = AgentMessageRequest(
        channel="whatsapp",
        conversation_id="conv-prv012",
        customer={"external_id": "cust-12"},
        message={"content": "Hola"},
    )
    response = agent_runtime.process_stateless_agent_message("tenant-prv", request)
    assert "Inteligencia Artificial" in response.reply.content
    assert "Art. 50" in response.ai_disclosure


def test_prv021_sensitive_or_minor_message_triggers_human_handoff_without_llm(monkeypatch):
    def fail_if_http_called(**_kwargs):
        raise AssertionError("External LLM must NOT be called when sensitive/minor data is detected")

    settings = Settings(_env_file=None, chat_provider="groq", groq_api_key=SecretStr("synthetic-key"))
    monkeypatch.setattr(httpx, "Client", fail_if_http_called)
    monkeypatch.setattr(agent_runtime, "get_settings", lambda: settings)
    request = AgentMessageRequest(
        channel="whatsapp",
        conversation_id="conv-prv021",
        customer={"external_id": "cust-21"},
        message={"content": "Hola, tengo 16 años y quiero consultar por mi diagnóstico médico."},
    )
    response = agent_runtime.process_stateless_agent_message("tenant-prv", request)
    assert response.requires_human is True
    assert response.next_step == "handoff"
    assert response.actions[0].payload.get("reason") == "sensitive_data_detected"
