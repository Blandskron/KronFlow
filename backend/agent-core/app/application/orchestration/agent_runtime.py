from decimal import Decimal
import logging
import re
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.agent import AgentActionPayload, AgentMessageRequest, AgentMessageResponse, ReplyPayload, SourcePayload
from app.application.orchestration.chat_prompt import build_context_prompt
from app.core.config import Settings, get_settings
from app.domain.ports.llm import ChatInputBudgetExceeded
from app.infrastructure.external_tools.mock_tools import TYPED_PROPOSAL_ACTIONS, prepare_action
from app.infrastructure.llm.groq import GroqClient
from app.infrastructure.llm.pricing import estimate_cost_usd
from app.infrastructure.operational_context import OperationalContextSource, operational_context_client
from app.infrastructure.vector_store.simple_retriever import RetrievedSource, retrieve_sources
from app.models.agent import AgentResponseTrace
from app.models.conversation import ConversationMessage, ConversationSession, RetrievalTrace


logger = logging.getLogger(__name__)
GREETING_RE = re.compile(r"^[¡¿\s]*(hola|buenas|buenos dias|buenos días|buenas tardes|buenas noches|hello|hi)\s*[!.?¿¡]*\s*$", re.IGNORECASE)
THANKS_RE = re.compile(r"^[¡¿\s]*(muchas gracias|gracias|muchísimas gracias)\s*[!.?¿¡]*\s*$", re.IGNORECASE)
HANDOFF_RE = re.compile(
    r"^[¡¿\s]*(?:(?:quiero|necesito|quisiera|puedo|me gustaría)\s+)?hablar con\s+"
    r"(?:(?:un|una|alguien de)\s+)?(?:persona|humano|humana|ejecutiv[oa]|asesor[ao]|tu equipo|el equipo)\b",
    re.IGNORECASE,
)
CONTEXT_INSTRUCTIONS = (
    "Eres el agente empresarial de Flowkron. Responde de forma breve, segura y honesta. "
    "Usa solo el contexto proporcionado para afirmar datos de la empresa. "
    "Si el contexto no alcanza, pide más información o deriva al equipo."
)


def _safe_resolve_agent(tenant_id: str, payload: AgentMessageRequest) -> dict[str, Any] | None:
    explicit = payload.agent_id is not None or payload.agent_revision_id is not None
    if not explicit and not get_settings().internal_token.strip():
        return None
    try:
        resolved = operational_context_client.resolve_active_agent(
            tenant_id,
            agent_id=payload.agent_id,
            agent_revision_id=payload.agent_revision_id,
        )
    except HTTPException as exc:
        if explicit and exc.status_code < 500:
            raise
        return None
    except Exception:
        return None
    return resolved if isinstance(resolved, dict) and "agent_revision_id" in resolved else None


def _safe_load_ai_policy(tenant_id: str) -> dict[str, Any]:
    """Privacy by Default (PRV-004): fail closed when tenant policy is unavailable."""
    default_policy = {
        "ai_enabled": True,
        "allow_external_ai_transfer": False,
        "memory_auto_capture": False,
    }
    if not get_settings().internal_token.strip():
        return default_policy
    try:
        policy = operational_context_client.get_tenant_ai_policy(tenant_id)
    except Exception:
        return default_policy
    if not isinstance(policy, dict):
        return default_policy
    return {
        "ai_enabled": bool(policy.get("ai_enabled", True)),
        "allow_external_ai_transfer": bool(policy.get("allow_external_ai_transfer", False)),
        "memory_auto_capture": bool(policy.get("memory_auto_capture", False)),
    }


def _safe_load_memory(tenant_id: str, conversation_id: str, *, allow_memory: bool = False) -> list[dict[str, Any]]:
    if not allow_memory or not get_settings().internal_token.strip():
        return []
    try:
        items = operational_context_client.list_conversation_memory(tenant_id, conversation_id, limit=10)
    except Exception:
        return []
    if not isinstance(items, list):
        return []
    return [
        item for item in items
        if isinstance(item, dict) and isinstance(item.get("memory_key"), str) and isinstance(item.get("memory_value"), str)
    ]


def _build_instructions(active_agent: dict[str, Any] | None, memory_items: list[dict[str, Any]]) -> str:
    base = CONTEXT_INSTRUCTIONS
    if active_agent:
        parts = [f"Eres {active_agent.get('name', 'el agente')} ({active_agent.get('role', 'assistant')}), tono {active_agent.get('tone', 'professional')}."]
        if active_agent.get("instructions"):
            parts.append(str(active_agent["instructions"]).strip())
        else:
            parts.append(CONTEXT_INSTRUCTIONS)
        base = "\n".join(parts)
    if memory_items:
        lines = [f"- {item['memory_key']}: {item['memory_value']}" for item in memory_items[:5]]
        memory_block = "\n\nMemoria de conversación:\n" + "\n".join(lines)
        if len(memory_block) <= 1500:
            base = base + memory_block
    return base


def _record_usage_best_effort(
    tenant_id: str,
    llm: GroqClient,
    *,
    is_simulation: bool,
    agent_id: int | None,
    agent_revision_id: int | None,
) -> None:
    obs = llm.last_observation
    if obs is None or not get_settings().internal_token.strip():
        return
    cost, pricing_version = estimate_cost_usd(obs.model, obs.prompt_tokens, obs.completion_tokens)
    try:
        operational_context_client.record_ai_usage(
            tenant_id,
            provider=obs.provider,
            model=obs.model,
            prompt_tokens=obs.prompt_tokens or 0,
            completion_tokens=obs.completion_tokens or 0,
            latency_ms=obs.latency_ms,
            estimated_cost_usd=cost if obs.prompt_tokens is not None else Decimal("0.000000"),
            is_simulation=is_simulation,
            agent_id=agent_id,
            agent_revision_id=agent_revision_id,
            pricing_version=pricing_version,
        )
    except Exception:
        logger.debug("ai_usage_record outcome=skipped")


def _record_trace_best_effort(tenant_id: str, payload: AgentMessageRequest, response: AgentMessageResponse, *, is_simulation: bool) -> None:
    if not get_settings().internal_token.strip():
        return
    try:
        operational_context_client.record_trace(
            tenant_id,
            {
                "conversation_id": payload.conversation_id,
                "agent_id": response.agent_id,
                "agent_revision_id": response.agent_revision_id,
                "query": payload.message.content,
                "output_message": response.reply.content,
                "confidence": response.confidence,
                "requires_human": response.requires_human,
                "is_simulation": is_simulation,
                "sources": [s.model_dump() for s in response.sources],
                "actions": [a.model_dump() for a in response.actions],
            },
        )
    except Exception:
        logger.debug("trace_record outcome=skipped")


def _maybe_prepare_typed_proposal(
    tenant_id: str,
    payload: AgentMessageRequest,
    *,
    active_agent: dict[str, Any] | None,
    handoff_reason: str | None,
    is_simulation: bool,
) -> list[AgentActionPayload]:
    raw_payload = payload.metadata.raw_payload or {}
    allowed_tools = set(active_agent.get("allowed_tools") or []) if active_agent else None
    proposed = raw_payload.get("proposed_action")

    if isinstance(proposed, dict) and isinstance(proposed.get("type"), str):
        action_type = proposed["type"]
        args = proposed.get("arguments") or proposed.get("payload") or {}
        if allowed_tools is not None and action_type not in allowed_tools:
            return [prepare_action("none", {"reason": "tool_not_authorized"})]
        prepared = prepare_action(action_type, args if isinstance(args, dict) else {})
        if (
            not is_simulation
            and prepared.type in TYPED_PROPOSAL_ACTIONS
            and isinstance(proposed.get("resource_id"), int)
            and proposed["resource_id"] >= 1
        ):
            try:
                operational_context_client.create_proposal(
                    tenant_id,
                    {
                        "action_type": prepared.type,
                        "resource_id": proposed["resource_id"],
                        "arguments": prepared.payload,
                        "idempotency_key": str(proposed.get("idempotency_key") or f"turn:{payload.conversation_id}:{prepared.type}"),
                        "proposed_by": f"agent:{active_agent['agent_id']}" if active_agent else "agent-core",
                        "rationale": proposed.get("rationale") or "Propuesta generada durante el turno conversacional",
                    },
                )
            except Exception:
                logger.debug("proposal_create outcome=skipped")
        return [prepared]

    if handoff_reason:
        if (
            not is_simulation
            and isinstance(raw_payload.get("operational_conversation_id"), int)
            and raw_payload["operational_conversation_id"] >= 1
            and (allowed_tools is None or not allowed_tools or "crm.conversation.request_handoff" in allowed_tools or "handoff_human" in allowed_tools)
        ):
            try:
                operational_context_client.create_proposal(
                    tenant_id,
                    {
                        "action_type": "crm.conversation.request_handoff",
                        "resource_id": raw_payload["operational_conversation_id"],
                        "arguments": {"reason": str(handoff_reason)[:180]},
                        "idempotency_key": f"handoff:{payload.conversation_id}:{handoff_reason}",
                        "proposed_by": f"agent:{active_agent['agent_id']}" if active_agent else "agent-core",
                        "rationale": f"Derivación automática: {handoff_reason}",
                    },
                )
            except Exception:
                logger.debug("handoff_proposal outcome=skipped")
        return [prepare_action("handoff_human", {"reason": handoff_reason})]

    return [prepare_action("none", {})]


def process_stateless_agent_message(
    tenant_id: str,
    payload: AgentMessageRequest,
    *,
    is_simulation: bool = False,
) -> AgentMessageResponse:
    message = payload.message.content
    if payload.agent_id is None and payload.agent_revision_id is None:
        if _is_greeting(message):
            return _reply(
                tenant_id,
                payload,
                "¡Hola! Soy el asistente de Inteligencia Artificial de este espacio. ¿En qué te puedo ayudar? (Puedes pedir hablar con una persona en cualquier momento).",
            )
        if THANKS_RE.fullmatch(message):
            return _reply(tenant_id, payload, "¡De nada! Si tienes otra consulta, estoy aquí para ayudarte.")
        if HANDOFF_RE.match(message):
            return _reply(
                tenant_id, payload, "Claro. Dejaré tu solicitud pendiente para que la revise el equipo.",
                handoff_reason="customer_requested_human",
            )

    active_agent = _safe_resolve_agent(tenant_id, payload)
    agent_id = active_agent["agent_id"] if active_agent else payload.agent_id
    agent_rev_id = active_agent["agent_revision_id"] if active_agent else payload.agent_revision_id

    if _is_greeting(message):
        return _reply(
            tenant_id,
            payload,
            "¡Hola! Soy el asistente de Inteligencia Artificial de este espacio. ¿En qué te puedo ayudar? (Puedes pedir hablar con una persona en cualquier momento).",
            agent_id=agent_id,
            agent_revision_id=agent_rev_id,
        )
    if THANKS_RE.fullmatch(message):
        return _reply(tenant_id, payload, "¡De nada! Si tienes otra consulta, estoy aquí para ayudarte.", agent_id=agent_id, agent_revision_id=agent_rev_id)
    if HANDOFF_RE.match(message):
        return _reply(
            tenant_id, payload, "Claro. Dejaré tu solicitud pendiente para que la revise el equipo.",
            handoff_reason="customer_requested_human", agent_id=agent_id, agent_revision_id=agent_rev_id,
            active_agent=active_agent, is_simulation=is_simulation,
        )

    doc_ids = active_agent.get("allowed_document_ids") if active_agent else None
    try:
        if doc_ids:
            sources = operational_context_client.retrieve_sources(tenant_id, message, document_ids=doc_ids)
        else:
            sources = operational_context_client.retrieve_sources(tenant_id, message)
    except HTTPException as error:
        if error.status_code < 500:
            raise
        response = _context_unavailable(tenant_id, payload, agent_id=agent_id, agent_revision_id=agent_rev_id)
        _record_trace_best_effort(tenant_id, payload, response, is_simulation=is_simulation)
        return response
    except (KeyError, TypeError, ValueError):
        response = _context_unavailable(tenant_id, payload, agent_id=agent_id, agent_revision_id=agent_rev_id)
        _record_trace_best_effort(tenant_id, payload, response, is_simulation=is_simulation)
        return response

    ai_policy = _safe_load_ai_policy(tenant_id)
    memory_items = _safe_load_memory(
        tenant_id,
        payload.conversation_id,
        allow_memory=bool(ai_policy.get("memory_auto_capture", False)),
    )
    response = _contextual_reply(
        tenant_id,
        payload,
        sources,
        get_settings(),
        source_prefix="context-document",
        source_limit=3,
        active_agent=active_agent,
        memory_items=memory_items,
        allow_external_ai_transfer=bool(ai_policy.get("allow_external_ai_transfer", False)),
        is_simulation=is_simulation,
        record_usage=True,
    )
    _record_trace_best_effort(tenant_id, payload, response, is_simulation=is_simulation)
    return response


def _context_unavailable(
    tenant_id: str,
    payload: AgentMessageRequest,
    *,
    agent_id: int | None = None,
    agent_revision_id: int | None = None,
) -> AgentMessageResponse:
    logger.info("context_retrieval outcome=unavailable")
    return _reply(
        tenant_id, payload, "No pude consultar el contexto de la empresa. Dejaré la consulta para que la revise el equipo.",
        handoff_reason="context_unavailable", confidence=0.0, agent_id=agent_id, agent_revision_id=agent_revision_id,
    )


def _contextual_reply(
    tenant_id: str,
    payload: AgentMessageRequest,
    sources: list[OperationalContextSource] | list[RetrievedSource],
    settings: Settings,
    *,
    source_prefix: str,
    source_limit: int,
    active_agent: dict[str, Any] | None = None,
    memory_items: list[dict[str, Any]] | None = None,
    allow_external_ai_transfer: bool = False,
    is_simulation: bool = False,
    record_usage: bool = False,
) -> AgentMessageResponse:
    confidence = sources[0].score if sources else 0.0
    handoff_reason = None
    llm = GroqClient(settings)
    agent_id = active_agent["agent_id"] if active_agent else payload.agent_id
    agent_rev_id = active_agent["agent_revision_id"] if active_agent else payload.agent_revision_id
    instructions = _build_instructions(active_agent, memory_items or [])

    if not sources or confidence < settings.low_confidence_threshold:
        handoff_reason = "insufficient_context"
        reply_content = (
            "No cuento con información suficiente para responder tu solicitud de forma precisa. "
            "Dejaré tu solicitud pendiente para que la revise el equipo."
        )
    elif not llm.enabled_for_chat or not allow_external_ai_transfer:
        if llm.enabled_for_chat and not allow_external_ai_transfer:
            logger.info("external_ai_egress outcome=blocked_by_policy tenant_id=%s", tenant_id)
        reply_content = f"Según el contexto disponible: {sources[0].content[:700]}"
        sources = sources[:1]
    else:
        try:
            messages, used = build_context_prompt(
                instructions, payload.message.content,
                [source.content for source in sources[:source_limit]], settings.chat_input_max_chars,
            )
            reply_content = llm.complete(messages)
            sources = sources[:used]
            if record_usage:
                _record_usage_best_effort(
                    tenant_id, llm, is_simulation=is_simulation, agent_id=agent_id, agent_revision_id=agent_rev_id,
                )
        except ChatInputBudgetExceeded:
            logger.info("context_prompt outcome=input_budget_exceeded")
            handoff_reason = "chat_input_budget_exceeded"
            reply_content = "La consulta requiere revisión. Dejaré tu solicitud pendiente para el equipo."
            confidence = 0.0
        except (httpx.HTTPError, IndexError, KeyError, TypeError, ValueError, RuntimeError):
            handoff_reason = "chat_provider_unavailable"
            reply_content = "No pude consultar el proveedor de IA. Dejaré tu solicitud pendiente para el equipo."
            confidence = 0.0

    source_payloads = [
        SourcePayload(
            source_id=f"{source_prefix}:{source.document_id}:chunk:{source.chunk_id}",
            document_id=str(source.document_id), chunk_id=str(source.chunk_id), title=source.title, score=source.score,
        )
        for source in sources
    ]
    return _reply(
        tenant_id,
        payload,
        reply_content,
        handoff_reason=handoff_reason,
        confidence=confidence,
        sources=source_payloads,
        agent_id=agent_id,
        agent_revision_id=agent_rev_id,
        active_agent=active_agent,
        is_simulation=is_simulation,
    )


def _reply(
    tenant_id: str,
    payload: AgentMessageRequest,
    content: str,
    *,
    handoff_reason: str | None = None,
    confidence: float = 1.0,
    sources: list[SourcePayload] | None = None,
    agent_id: int | None = None,
    agent_revision_id: int | None = None,
    active_agent: dict[str, Any] | None = None,
    is_simulation: bool = False,
) -> AgentMessageResponse:
    actions = _maybe_prepare_typed_proposal(
        tenant_id,
        payload,
        active_agent=active_agent,
        handoff_reason=handoff_reason,
        is_simulation=is_simulation,
    )
    return AgentMessageResponse(
        tenant_id=tenant_id,
        conversation_id=payload.conversation_id,
        reply=ReplyPayload(content=content),
        actions=actions,
        requires_human=handoff_reason is not None,
        confidence=confidence,
        sources=sources or [],
        next_step="handoff" if handoff_reason else "continue_conversation",
        agent_id=agent_id,
        agent_revision_id=agent_revision_id,
    )


def _is_greeting(value: str) -> bool:
    return bool(GREETING_RE.match(value.strip()))


def process_agent_message(db: Session, tenant_id: str, payload: AgentMessageRequest) -> AgentMessageResponse:
    conversation = db.scalar(
        select(ConversationSession).where(
            ConversationSession.tenant_id == tenant_id,
            ConversationSession.channel == payload.channel,
            ConversationSession.external_conversation_id == payload.conversation_id,
        )
    )
    if not conversation:
        conversation = ConversationSession(
            tenant_id=tenant_id,
            channel=payload.channel,
            external_conversation_id=payload.conversation_id,
            customer_external_id=payload.customer.external_id,
            customer_name=payload.customer.name,
            customer_phone=payload.customer.phone,
            customer_email=payload.customer.email,
        )
        db.add(conversation)
        db.flush()

    db.add(
        ConversationMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            sender_type="customer",
            message_type=payload.message.type,
            content=payload.message.content,
            attachments=payload.message.attachments,
            raw_payload=payload.metadata.raw_payload,
        )
    )

    response = _contextual_reply(
        tenant_id, payload, retrieve_sources(db, tenant_id, payload.message.content), get_settings(),
        source_prefix="document", source_limit=1,
    )
    reply_content = response.reply.content
    sources = [source.model_dump() for source in response.sources]
    db.add(
        ConversationMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            sender_type="agent",
            message_type="text",
            content=reply_content,
            attachments=[],
            raw_payload={"sources": sources},
        )
    )
    db.add(RetrievalTrace(tenant_id=tenant_id, conversation_id=conversation.id, query=payload.message.content,
                          sources=sources, confidence=response.confidence))
    db.add(AgentResponseTrace(tenant_id=tenant_id, conversation_id=conversation.id, input_message=payload.message.content,
                              output_message=reply_content, confidence=response.confidence, sources=sources))
    conversation.requires_human = response.requires_human
    db.commit()
    return response
