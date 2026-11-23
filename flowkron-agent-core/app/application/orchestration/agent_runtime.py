import logging
import re

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.agent import AgentMessageRequest, AgentMessageResponse, ReplyPayload, SourcePayload
from app.application.orchestration.chat_prompt import build_context_prompt
from app.core.config import Settings, get_settings
from app.domain.ports.llm import ChatInputBudgetExceeded
from app.infrastructure.external_tools.mock_tools import prepare_action
from app.infrastructure.llm.groq import GroqClient
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


def process_stateless_agent_message(tenant_id: str, payload: AgentMessageRequest) -> AgentMessageResponse:
    message = payload.message.content
    if _is_greeting(message):
        return _reply(tenant_id, payload, "¡Hola! Soy el asistente de este espacio. ¿En qué te puedo ayudar?")
    if THANKS_RE.fullmatch(message):
        return _reply(tenant_id, payload, "¡De nada! Si tienes otra consulta, estoy aquí para ayudarte.")
    if HANDOFF_RE.match(message):
        return _reply(
            tenant_id, payload, "Claro. Dejaré tu solicitud pendiente para que la revise el equipo.",
            handoff_reason="customer_requested_human",
        )
    try:
        sources = operational_context_client.retrieve_sources(tenant_id, message)
    except HTTPException as error:
        if error.status_code < 500:
            raise
        return _context_unavailable(tenant_id, payload)
    except (KeyError, TypeError, ValueError):
        return _context_unavailable(tenant_id, payload)
    return _contextual_reply(tenant_id, payload, sources, get_settings(), source_prefix="context-document", source_limit=3)


def _context_unavailable(tenant_id: str, payload: AgentMessageRequest) -> AgentMessageResponse:
    logger.info("context_retrieval outcome=unavailable")
    return _reply(
        tenant_id, payload, "No pude consultar el contexto de la empresa. Dejaré la consulta para que la revise el equipo.",
        handoff_reason="context_unavailable", confidence=0.0,
    )


def _contextual_reply(
    tenant_id: str, payload: AgentMessageRequest, sources: list[OperationalContextSource] | list[RetrievedSource],
    settings: Settings, *, source_prefix: str, source_limit: int,
) -> AgentMessageResponse:
    confidence = sources[0].score if sources else 0.0
    handoff_reason = None
    llm = GroqClient(settings)
    if not sources or confidence < settings.low_confidence_threshold:
        handoff_reason = "insufficient_context"
        reply_content = (
            "No cuento con información suficiente para responder tu solicitud de forma precisa. "
            "Dejaré tu solicitud pendiente para que la revise el equipo."
        )
    elif not llm.enabled_for_chat:
        reply_content = f"Según el contexto disponible: {sources[0].content[:700]}"
        sources = sources[:1]
    else:
        try:
            messages, used = build_context_prompt(
                CONTEXT_INSTRUCTIONS, payload.message.content,
                [source.content for source in sources[:source_limit]], settings.chat_input_max_chars,
            )
            reply_content = llm.complete(messages)
            sources = sources[:used]
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
        tenant_id, payload, reply_content, handoff_reason=handoff_reason, confidence=confidence, sources=source_payloads,
    )


def _reply(
    tenant_id: str, payload: AgentMessageRequest, content: str, *, handoff_reason: str | None = None,
    confidence: float = 1.0, sources: list[SourcePayload] | None = None,
) -> AgentMessageResponse:
    action = prepare_action("handoff_human", {"reason": handoff_reason}) if handoff_reason else prepare_action("none", {})
    return AgentMessageResponse(
        tenant_id=tenant_id,
        conversation_id=payload.conversation_id,
        reply=ReplyPayload(content=content),
        actions=[action],
        requires_human=handoff_reason is not None,
        confidence=confidence,
        sources=sources or [],
        next_step="handoff" if handoff_reason else "continue_conversation",
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
