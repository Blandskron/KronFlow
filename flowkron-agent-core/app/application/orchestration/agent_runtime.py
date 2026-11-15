import httpx
import re
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.schemas.agent import AgentActionPayload, AgentMessageRequest, AgentMessageResponse, ReplyPayload, SourcePayload
from app.core.config import get_settings
from app.domain.ports.llm import ChatMessage
from app.infrastructure.external_tools.mock_tools import prepare_action
from app.infrastructure.llm.azure_openai import AzureOpenAIClient
from app.infrastructure.operational_context import operational_context_client
from app.infrastructure.vector_store.simple_retriever import retrieve_sources
from app.models.agent import AgentResponseTrace
from app.models.conversation import ConversationMessage, ConversationSession, RetrievalTrace


GREETING_RE = re.compile(r"^\s*(hola|buenas|buenos dias|buenos días|buenas tardes|buenas noches|hello|hi)\s*[!.?¿¡]*\s*$", re.IGNORECASE)


def process_stateless_agent_message(tenant_id: str, payload: AgentMessageRequest) -> AgentMessageResponse:
    settings = get_settings()
    llm = AzureOpenAIClient(settings)
    sources = operational_context_client.retrieve_sources(tenant_id, payload.message.content)
    confidence = sources[0].score if sources else 0.0
    source_payloads = [
        SourcePayload(
            source_id=f"context-document:{source.document_id}:chunk:{source.chunk_id}",
            document_id=str(source.document_id),
            chunk_id=str(source.chunk_id),
            title=source.title,
            score=source.score,
        )
        for source in sources
    ]
    if sources and llm.enabled_for_chat:
        try:
            context = "\n\n".join(source.content for source in sources[:3])
            user_content = payload.message.content if not context else f"Contexto:\n{context}\n\nPregunta:\n{payload.message.content}"
            reply_content = llm.complete(
                [
                    ChatMessage(
                        role="system",
                        content=(
                            "Eres el agente empresarial omnicanal de Flowkron. "
                            "Responde de forma breve, segura y honesta. "
                            "Si no tienes contexto documental, no inventes datos y pide mas informacion o deriva."
                        ),
                    ),
                    ChatMessage(role="user", content=user_content),
                ]
            )
        except (httpx.HTTPError, KeyError, ValueError, RuntimeError):
            reply_content = (
                "No pude consultar el proveedor de IA en este momento. "
                "Puedo derivar la conversacion a un humano."
            )
    else:
        reply_content = (
            "No cuento con información suficiente para responder tu solicitud de forma precisa. "
            "Te transferiré con uno de nuestros ejecutivos para que pueda ayudarte correctamente."
        )
    if not sources and _is_greeting(payload.message.content):
        status_payload = operational_context_client.get_status(tenant_id)
        if int(status_payload.get("active_documents_count") or 0) > 0:
            return AgentMessageResponse(
                tenant_id=tenant_id,
                conversation_id=payload.conversation_id,
                reply=ReplyPayload(
                    content=(
                        "Hola. Ya tengo contexto empresarial cargado. "
                        "Puedes preguntarme sobre la empresa, servicios, politicas o preguntas frecuentes."
                    )
                ),
                actions=[prepare_action("none", {})],
                requires_human=False,
                confidence=max(settings.low_confidence_threshold, 0.4),
                sources=[],
                next_step="continue_conversation",
            )
    return AgentMessageResponse(
        tenant_id=tenant_id,
        conversation_id=payload.conversation_id,
        reply=ReplyPayload(content=reply_content),
        actions=[prepare_action("none", {})] if sources else [prepare_action("handoff_human", {"reason": "operational_context_adapter_pending"})],
        requires_human=not bool(sources),
        confidence=confidence,
        sources=source_payloads,
        next_step="continue_conversation" if sources else "handoff",
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

    sources = retrieve_sources(db, tenant_id, payload.message.content)
    confidence = sources[0].score if sources else 0.0
    settings = get_settings()
    llm = AzureOpenAIClient(settings)
    requires_human = confidence < settings.low_confidence_threshold
    if sources:
        source_text = sources[0].content[:700]
        if llm.enabled_for_chat:
            try:
                reply_content = llm.complete(
                    [
                        ChatMessage(
                            role="system",
                            content=(
                                "Responde usando solo el contexto verificado. "
                                "Si el contexto no alcanza, dilo claramente y recomienda derivacion."
                            ),
                        ),
                        ChatMessage(role="user", content=f"Contexto:\n{source_text}\n\nPregunta:\n{payload.message.content}"),
                    ]
                )
            except (httpx.HTTPError, KeyError, ValueError, RuntimeError):
                reply_content = f"Segun el contexto disponible: {source_text}"
        else:
            reply_content = f"Segun el contexto disponible: {source_text}"
        next_step = "continue_conversation"
        actions: list[AgentActionPayload] = [prepare_action("none", {})]
    else:
        reply_content = (
            "No tengo suficiente contexto verificado para responder con seguridad. "
            "Puedo pedir mas informacion o derivar la conversacion a un humano."
        )
        next_step = "handoff"
        actions = [prepare_action("handoff_human", {"reason": "insufficient_context"})]

    source_payloads = [
        SourcePayload(
            source_id=f"document:{source.document_id}:chunk:{source.chunk_id}",
            document_id=str(source.document_id),
            chunk_id=str(source.chunk_id),
            title=source.title,
            score=source.score,
        )
        for source in sources
    ]
    db.add(
        ConversationMessage(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            sender_type="agent",
            message_type="text",
            content=reply_content,
            attachments=[],
            raw_payload={"sources": [source.model_dump() for source in source_payloads]},
        )
    )
    db.add(RetrievalTrace(tenant_id=tenant_id, conversation_id=conversation.id, query=payload.message.content, sources=[s.model_dump() for s in source_payloads], confidence=confidence))
    db.add(AgentResponseTrace(tenant_id=tenant_id, conversation_id=conversation.id, input_message=payload.message.content, output_message=reply_content, confidence=confidence, sources=[s.model_dump() for s in source_payloads]))
    conversation.requires_human = requires_human
    db.commit()

    return AgentMessageResponse(
        tenant_id=tenant_id,
        conversation_id=payload.conversation_id,
        reply=ReplyPayload(content=reply_content),
        actions=actions,
        requires_human=requires_human,
        confidence=confidence,
        sources=source_payloads,
        next_step=next_step,
    )
