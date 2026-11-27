"""Idempotent synthetic demo dataset seeder (used exclusively by compose.demo.yaml)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_resolver import TenantContext
from app.schemas.agent import AgentConfigureRequest
from app.schemas.context import AgentRuleCreateIn
from app.schemas.webchat import WebchatWidgetCreateIn
from app.schemas.workflow import WorkflowCreateIn, WorkflowGraphIn
from app.services.agent_service import configure_agent, publish_agent
from app.services.ai_extensions_service import record_ai_usage
from app.services.ai_proposal_service import create_ai_proposal
from app.services.campaign_service import create_campaign, create_template_with_version
from app.services.channel_connection_service import create_channel_connection
from app.services.consent_authorization_service import record_consent_decision, record_suppression
from app.services.context_service import create_agent_rule
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.opportunity_service import create_opportunity, list_pipeline_stages, update_opportunity
from app.services.tenant_data import bind_tenant_session
from app.services.tool_hub_service import ensure_builtin_tools
from app.services.webchat_service import create_webchat_widget
from app.services.workflow_service import create_workflow, publish_workflow
from app.tenant_models.contact_capture import ContactPoint
from app.tenant_models.conversation_control import ConversationControl
from app.tenant_models.operations import (
    Cliente,
    ConversacionResumen,
    Conversation,
    Lead,
    Message,
    SolicitudDerecho,
)


def seed_demo_tenant_data(
    db: Session,
    tenant: TenantContext,
    *,
    actor_user_id: str = "demo-bootstrap",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Populate a fresh demo tenant with realistic synthetic data across all CRM modules.

    Strictly idempotent: if any contact already exists in the tenant schema, returns without changes.
    """
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    bind_tenant_session(db, tenant.schema_name)

    if db.scalar(select(Cliente.id).limit(1)) is not None:
        return {"seeded": False, "already_populated": True, "counts": {}}

    # 1. Contacts & Leads
    demo_contacts = [
        {
            "rut": "18.450.120-4",
            "nombre": "Sofía Rojas",
            "email": "sofia.rojas@nortech.example",
            "telefono": "+56981234501",
            "whatsapp_id": "56981234501@s.whatsapp.net",
            "tipo_cliente": "activo",
            "canal_origen": "whatsapp_directo",
            "consent": True,
            "score": 92,
            "clasificacion": "caliente",
            "plazo": "esta_semana",
            "estado": "en_proceso",
            "resumen": "Busca automatizar atención WhatsApp + CRM para 12 ejecutivos en Santiago.",
        },
        {
            "rut": "16.920.331-K",
            "nombre": "Matías Fernández",
            "email": "matias.fernandez@andeslog.example",
            "telefono": "+56981234502",
            "whatsapp_id": "56981234502@s.whatsapp.net",
            "tipo_cliente": "prospecto",
            "canal_origen": "web_form",
            "consent": True,
            "score": 78,
            "clasificacion": "caliente",
            "plazo": "este_mes",
            "estado": "contactado",
            "resumen": "Solicitó demo de workflows DAG y trazabilidad de propuestas IA.",
        },
        {
            "rut": "19.110.845-2",
            "nombre": "Camila Herrera",
            "email": "camila.herrera@australpay.example",
            "telefono": "+56981234503",
            "whatsapp_id": "56981234503@s.whatsapp.net",
            "tipo_cliente": "activo",
            "canal_origen": "instagram",
            "consent": True,
            "score": 85,
            "clasificacion": "caliente",
            "plazo": "este_dia",
            "estado": "ganado",
            "resumen": "Plan Enterprise aprobado con integración de webhooks y multi-agente.",
        },
        {
            "rut": "15.740.219-8",
            "nombre": "Diego Morales",
            "email": "diego.morales@pacifico.example",
            "telefono": "+56981234504",
            "whatsapp_id": "56981234504@s.whatsapp.net",
            "tipo_cliente": "prospecto",
            "canal_origen": "whatsapp_directo",
            "consent": True,
            "score": 58,
            "clasificacion": "tibio",
            "plazo": "tres_meses",
            "estado": "nuevo",
            "resumen": "Consultó por integración con catálogo y webchat embebible.",
        },
        {
            "rut": "17.305.910-5",
            "nombre": "Valentina Castro",
            "email": "valentina.castro@cordillera.example",
            "telefono": "+56981234505",
            "whatsapp_id": "56981234505@s.whatsapp.net",
            "tipo_cliente": "recurrente",
            "canal_origen": "webchat",
            "consent": True,
            "score": 66,
            "clasificacion": "tibio",
            "plazo": "cotizando",
            "estado": "contactado",
            "resumen": "Cliente actual evaluando ampliar licencias y activar campañas de correo.",
        },
        {
            "rut": "14.880.602-1",
            "nombre": "Tomás Navarro",
            "email": "tomas.navarro@surretail.example",
            "telefono": "+56981234506",
            "whatsapp_id": "56981234506@s.whatsapp.net",
            "tipo_cliente": "perdido",
            "canal_origen": "whatsapp_directo",
            "consent": False,
            "score": 22,
            "clasificacion": "frio",
            "plazo": "explorando",
            "estado": "perdido",
            "resumen": "Solicitó baja de comunicaciones comerciales; mantiene registro histórico.",
        },
    ]

    contacts: list[Cliente] = []
    leads: list[Lead] = []
    for idx, item in enumerate(demo_contacts):
        created_at = current - timedelta(days=6 - idx, hours=2)
        c = Cliente(
            rut=item["rut"],
            nombre=item["nombre"],
            email=item["email"],
            telefono=item["telefono"],
            whatsapp_id=item["whatsapp_id"],
            tipo_cliente=item["tipo_cliente"],
            canal_origen=item["canal_origen"],
            consentimiento_datos=item["consent"],
            fecha_consentimiento=created_at if item["consent"] else None,
            canal_consentimiento=item["canal_origen"] if item["consent"] else None,
            version_politica="v1.0",
            creado_en=created_at,
            actualizado_en=created_at,
        )
        db.add(c)
        db.flush()
        contacts.append(c)

        db.add(
            ContactPoint(
                client_id=c.id,
                point_type="email",
                normalized_value=item["email"].lower(),
                status="active",
                verified=True,
                source="demo_seed",
                created_at=created_at,
            )
        )
        db.add(
            ContactPoint(
                client_id=c.id,
                point_type="whatsapp",
                normalized_value=item["whatsapp_id"],
                status="active",
                verified=True,
                source="demo_seed",
                created_at=created_at,
            )
        )

        lead = Lead(
            cliente_id=c.id,
            score_lead=item["score"],
            clasificacion=item["clasificacion"],
            plazo_compra=item["plazo"],
            requiere_credito=idx in (0, 2),
            estado=item["estado"],
            resumen_ia=item["resumen"],
            creado_en=created_at,
            actualizado_en=created_at + timedelta(hours=1),
        )
        db.add(lead)
        db.flush()
        leads.append(lead)

        publish_domain_event_in_tx(
            db,
            tenant,
            event_type="lead.created",
            aggregate_type="lead",
            aggregate_id=lead.id,
            payload={"lead_id": lead.id, "contact_id": c.id, "clasificacion": item["clasificacion"], "source": "demo_seed"},
            occurred_at=created_at,
        )

    db.commit()

    # Consent ledger + 1 opt-out suppression for realistic campaign preview testing
    for idx, c in enumerate(contacts):
        if demo_contacts[idx]["consent"]:
            record_consent_decision(
                db,
                tenant,
                client_id=c.id,
                channel="email",
                destination=c.email or "",
                purpose="marketing",
                granted=True,
                effective_at=current - timedelta(days=5),
                source="operational",
                policy_version="v1.0",
                actor_id=actor_user_id,
                recorded_at=current - timedelta(days=5),
            )
        else:
            record_suppression(
                db,
                tenant,
                channel="email",
                destination=c.email or "",
                purpose="marketing",
                reason="unsubscribe",
                source="operational",
                client_id=c.id,
                actor_id=actor_user_id,
                recorded_at=current - timedelta(days=1),
            )

    # 2. Conversations, Messages & HITL Controls
    bind_tenant_session(db, tenant.schema_name)
    demo_threads = [
        (
            contacts[0],
            "waiting_human",
            2,
            [
                ("usuario", "inbound", "Hola, necesitamos cotizar KronFlow para 12 ejecutivos con WhatsApp e integración CRM."),
                ("agente", "outbound", "¡Hola Sofía! Con gusto te ayudo. KronFlow soporta múltiples ejecutivos con control HITL y esquema aislado por empresa. ¿Prefieres una reunión esta semana?"),
                ("usuario", "inbound", "Sí, ideal mañana a las 11:00 con un ejecutivo comercial para revisar SLA y precios."),
            ],
        ),
        (
            contacts[1],
            "ai_active",
            0,
            [
                ("usuario", "inbound", "¿Puedo probar los flujos automáticos sin enviar mensajes reales a mis clientes?"),
                ("agente", "outbound", "Sí Matías, el motor de workflows DAG incluye simulación sin efectos y revisión de ramas antes de publicar."),
            ],
        ),
        (
            contacts[2],
            "human_active",
            0,
            [
                ("usuario", "inbound", "Confirmamos el contrato anual Enterprise. ¿Podemos agendar el onboarding técnico?"),
                ("agente", "outbound", "¡Excelente Camila! Dejé tu cuenta lista y nuestro equipo ya tomó el hilo para coordinar el kickoff."),
            ],
        ),
        (
            contacts[3],
            "ai_active",
            1,
            [
                ("usuario", "inbound", "Hola, ¿el webchat embebible funciona con orígenes restringidos y derivación a humano?"),
                ("agente", "outbound", "Sí Diego, cada widget valida orígenes exactos y mantiene continuidad completa al derivar a la bandeja HITL."),
            ],
        ),
    ]

    conv_ids: list[int] = []
    for t_idx, (contact, mode, unread, msgs) in enumerate(demo_threads):
        wa_id = contact.whatsapp_id or f"demo-{contact.id}"
        base_time = current - timedelta(hours=8 - t_idx * 2)
        conv = Conversation(
            session_id=wa_id,
            message={"type": "human", "content": msgs[0][2], "channel": "whatsapp"},
            creado_en=base_time,
        )
        db.add(conv)
        db.flush()
        conv_ids.append(conv.id)

        last_msg_text = msgs[-1][2]
        last_role = msgs[-1][0]
        last_time = base_time
        for m_idx, (rol, direction, body) in enumerate(msgs):
            ts = base_time + timedelta(minutes=m_idx * 6)
            last_time = ts
            db.add(
                Message(
                    whatsapp_id=wa_id,
                    rol=rol,
                    mensaje=body,
                    creado_en=ts,
                    connection_id="demo-wa",
                    channel="whatsapp",
                    external_message_id=f"demo-msg-{contact.id}-{m_idx}",
                    direction=direction,
                    message_type="text",
                    delivery_status="read" if direction == "outbound" else "received",
                    recorded_at=ts,
                )
            )

        db.add(
            ConversacionResumen(
                whatsapp_id=wa_id,
                nombre_cliente=contact.nombre,
                ultimo_mensaje=last_msg_text,
                ultimo_rol=last_role,
                ultimo_mensaje_en=last_time,
                total_mensajes=len(msgs),
                no_leidos=unread,
                actualizado_en=last_time,
            )
        )
        db.add(
            ConversationControl(
                conversation_id=conv.id,
                mode=mode,
                owner_user_id=actor_user_id if mode == "human_active" else None,
                ai_enabled=(mode == "ai_active"),
                control_version=1,
                handoff_reason="Solicitud de cotización Enterprise con ejecutivo" if mode == "waiting_human" else None,
                updated_by=actor_user_id,
                updated_at=last_time,
            )
        )

    db.commit()

    # 3. Pipeline Opportunities (stages auto-seeded by create_opportunity)
    opp_specs = [
        ("Despliegue CRM + WhatsApp Nortech (12 asientos)", contacts[0].id, leads[0].id, conv_ids[0], Decimal("4800000"), "CLP", None),
        ("Automatización Workflows DAG AndesLog", contacts[1].id, leads[1].id, conv_ids[1], Decimal("2950000"), "CLP", None),
        ("Licencia Enterprise Anual AustralPay", contacts[2].id, leads[2].id, conv_ids[2], Decimal("14400"), "USD", "won"),
        ("Piloto Webchat + RAG Pacífico", contacts[3].id, leads[3].id, conv_ids[3], Decimal("1600000"), "CLP", None),
        ("Expansión Campañas Email Cordillera", contacts[4].id, leads[4].id, None, Decimal("3200"), "USD", None),
    ]
    opportunities: list[dict] = []
    for title, cid, lid, convid, amount, currency, close_outcome in opp_specs:
        opp = create_opportunity(
            db,
            tenant,
            title=title,
            contact_id=cid,
            lead_id=lid,
            conversation_id=convid,
            owner_user_id=actor_user_id,
            amount=amount,
            currency=currency,
            actor_user_id=actor_user_id,
            now=current - timedelta(days=2),
        )
        opportunities.append(opp)

    stages = list_pipeline_stages(db, tenant)
    stage_by_slug = {s["slug"]: s["id"] for s in stages}
    if len(opportunities) >= 3 and "proposal" in stage_by_slug:
        update_opportunity(
            db,
            tenant,
            opportunities[0]["id"],
            expected_version=opportunities[0]["version"],
            stage_id=stage_by_slug["proposal"],
            note="Propuesta técnica enviada tras calificación inicial.",
            actor_user_id=actor_user_id,
            now=current - timedelta(hours=12),
        )
    if len(opportunities) >= 3 and "won" in stage_by_slug:
        update_opportunity(
            db,
            tenant,
            opportunities[2]["id"],
            expected_version=opportunities[2]["version"],
            stage_id=stage_by_slug["won"],
            outcome="won",
            close_reason="Contrato firmado y pago confirmado.",
            actor_user_id=actor_user_id,
            now=current - timedelta(hours=6),
        )

    # 4. Pending AI Action Proposals (for /app/ai-proposals)
    create_ai_proposal(
        db,
        tenant,
        action_type="crm.opportunity.add_note",
        resource_id=opportunities[0]["id"],
        arguments={"note": "Cliente confirmó disponibilidad mañana 11:00 para revisar SLA y pricing de 12 asientos."},
        idempotency_key="demo-prop-opp-note-1",
        proposed_by="agent-comercial-v1",
        rationale="Resumen detectado automáticamente en conversación WhatsApp de Sofía Rojas.",
        expires_at=current + timedelta(days=7),
        now=current - timedelta(hours=1),
    )
    create_ai_proposal(
        db,
        tenant,
        action_type="crm.contact.rename",
        resource_id=contacts[3].id,
        arguments={"name": "Diego Morales (Pacífico Retail)"},
        idempotency_key="demo-prop-contact-rename-1",
        proposed_by="agent-comercial-v1",
        rationale="El cliente indicó el nombre de su empresa en el hilo entrante.",
        expires_at=current + timedelta(days=7),
        now=current - timedelta(minutes=35),
    )

    # 5. Multi-Agent Platform (2 published agents + rules)
    ag_sales = configure_agent(
        db,
        tenant,
        AgentConfigureRequest(
            name="Asistente Comercial BLANDSKRON",
            role="Ventas consultivas y calificación",
            tone="professional",
            language="es",
            instructions=(
                "Atiende consultas comerciales sobre KronFlow, califica volumen de equipo y canales, "
                "cita fuentes del contexto empresarial y deriva a un ejecutivo humano ante solicitudes de cotización formal."
            ),
            allowed_tools=["handoff_human", "crm.opportunity.add_note", "crm.lead.update_stage"],
            is_default=True,
        ),
        actor_user_id=actor_user_id,
        now=current - timedelta(days=3),
    )
    ag_sales_pub = publish_agent(
        db,
        tenant,
        ag_sales["id"],
        expected_version=ag_sales["version"],
        note="Revisión inicial demo comercial",
        actor_user_id=actor_user_id,
        now=current - timedelta(days=3),
    )

    ag_support = configure_agent(
        db,
        tenant,
        AgentConfigureRequest(
            name="Especialista de Soporte y Agenda",
            role="Soporte técnico y agendamiento",
            tone="friendly",
            language="es",
            instructions=(
                "Ayuda a resolver dudas de configuración de WhatsApp, webchat y horarios de onboarding. "
                "Verifica disponibilidad antes de confirmar citas y escala incidencias críticas a soporte humano."
            ),
            allowed_tools=["handoff_human", "crm.conversation.request_handoff"],
            is_default=False,
        ),
        actor_user_id=actor_user_id,
        now=current - timedelta(days=2),
    )
    publish_agent(
        db,
        tenant,
        ag_support["id"],
        expected_version=ag_support["version"],
        note="Revisión inicial soporte demo",
        actor_user_id=actor_user_id,
        now=current - timedelta(days=2),
    )

    create_agent_rule(
        db,
        tenant,
        AgentRuleCreateIn(
            name="No prometer descuentos sin aprobación",
            rule_type="commercial_policy",
            content="Nunca comprometas descuentos ni SLA personalizados; crea una nota o deriva al equipo comercial.",
            priority=10,
            is_active=True,
            agent_id=ag_sales["id"],
        ),
    )
    create_agent_rule(
        db,
        tenant,
        AgentRuleCreateIn(
            name="Respetar bajas de consentimiento",
            rule_type="privacy",
            content="Ante cualquier solicitud de baja o privacidad, confirma el registro y detén seguimiento comercial.",
            priority=5,
            is_active=True,
            agent_id=ag_sales["id"],
        ),
    )

    # 6. Declarative DAG Workflows (1 published + 1 draft)
    wf_followup = create_workflow(
        db,
        tenant,
        WorkflowCreateIn(
            name="Seguimiento automático a leads nuevos",
            description="Espera 24 horas tras el alta del lead y notifica si no respondió ni se dio de baja.",
            trigger_event_type="lead.created",
            graph=WorkflowGraphIn(
                nodes=[
                    {"id": "t1", "type": "trigger", "label": "Lead creado", "config": {}},
                    {"id": "w1", "type": "wait", "label": "Esperar 24h", "config": {"delay_seconds": 86400}},
                    {"id": "a1", "type": "action", "label": "Notificar seguimiento", "config": {"action_kind": "notification.send", "channel": "email", "destination": "ventas@blandskron.example", "message": "Lead nuevo sin respuesta tras 24h."}},
                    {"id": "e1", "type": "end", "label": "Fin", "config": {}},
                ],
                edges=[
                    {"source": "t1", "target": "w1", "when": "always"},
                    {"source": "w1", "target": "a1", "when": "always"},
                    {"source": "a1", "target": "e1", "when": "always"},
                ],
            ),
        ),
        actor_user_id=actor_user_id,
        now=current - timedelta(days=2),
    )
    publish_workflow(db, tenant, wf_followup["id"], expected_version=wf_followup["draft_version"], note="Activado para demo", actor_user_id=actor_user_id, now=current - timedelta(days=2))

    create_workflow(
        db,
        tenant,
        WorkflowCreateIn(
            name="Calificación rápida de lead caliente",
            description="Evalúa temperatura caliente y propone actualización de etapa para revisión HITL.",
            trigger_event_type="lead.temperature.changed",
            graph=WorkflowGraphIn(
                nodes=[
                    {"id": "t1", "type": "trigger", "label": "Cambio de temperatura", "config": {}},
                    {"id": "c1", "type": "condition", "label": "¿Es caliente?", "config": {"field": "clasificacion", "operator": "eq", "value": "caliente"}},
                    {"id": "a1", "type": "action", "label": "Notificar ejecutivo", "config": {"action_kind": "notification.send", "channel": "email", "destination": "ventas@blandskron.example", "message": "Lead caliente listo para revisión comercial."}},
                    {"id": "e1", "type": "end", "label": "Fin", "config": {}},
                ],
                edges=[
                    {"source": "t1", "target": "c1", "when": "always"},
                    {"source": "c1", "target": "a1", "when": "true"},
                    {"source": "c1", "target": "e1", "when": "false"},
                    {"source": "a1", "target": "e1", "when": "always"},
                ],
            ),
        ),
        actor_user_id=actor_user_id,
        now=current - timedelta(days=1),
    )

    # 7. Campaigns & Delegated Email Channel (sandbox stub)
    conn = create_channel_connection(
        db,
        tenant,
        channel="email",
        provider="stub",
        sender_address="novedades@blandskron.example",
        display_name="Canal Email Sandbox BLANDSKRON",
        verified=True,
        sandbox_only=True,
        actor_user_id=actor_user_id,
        now=current - timedelta(days=2),
    )
    tmpl = create_template_with_version(
        db,
        tenant,
        name="Lanzamiento KronFlow v1.0",
        channel="email",
        language="es",
        subject="Novedades de automatización inteligente en KronFlow",
        body_text="Hola {{nombre}}, descubre las nuevas capacidades multi-agente y workflows DAG de KronFlow.",
        body_html="<p>Hola <strong>{{nombre}}</strong>,</p><p>Descubre las nuevas capacidades multi-agente y workflows DAG de KronFlow.</p>",
        declared_variables=["nombre"],
        approve_immediately=True,
        actor_user_id=actor_user_id,
        now=current - timedelta(days=2),
    )
    create_campaign(
        db,
        tenant,
        name="Campaña Demo Q4 · Lanzamiento Multi-Agente",
        channel="email",
        purpose="marketing",
        template_version_id=tmpl["template_version_id"],
        connection_id=conn["id"],
        timezone_iana="America/Santiago",
        actor_user_id=actor_user_id,
        now=current - timedelta(days=1),
    )

    # 8. Tool Hub + Embeddable Webchat Widget
    ensure_builtin_tools(db, tenant, now=current)
    create_webchat_widget(
        db,
        tenant,
        WebchatWidgetCreateIn(
            name="Widget Webchat Demo BLANDSKRON",
            allowed_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
            agent_id=ag_sales["id"],
            welcome_message="¡Hola! Soy el asistente demo de BLANDSKRON. ¿En qué te ayudo hoy?",
        ),
        actor_user_id=actor_user_id,
        now=current - timedelta(days=1),
    )

    # 9. Privacy Request (for /app/settings/privacy)
    bind_tenant_session(db, tenant.schema_name)
    db.add(
        SolicitudDerecho(
            whatsapp_id=contacts[5].whatsapp_id or "56981234506@s.whatsapp.net",
            tipo_derecho="portabilidad",
            estado="pendiente",
            fecha_solicitud=current - timedelta(hours=10),
            fecha_limite=current + timedelta(days=29),
            notas="Solicitud demo de exportación de datos personales para validación de bandeja de privacidad.",
        )
    )
    db.commit()

    # 10. AI Usage Records (for /app/analytics AI usage KPIs)
    for u_idx, (pt, ct, lat, cost) in enumerate(
        [
            (620, 185, 420, Decimal("0.0012")),
            (740, 210, 390, Decimal("0.0015")),
            (510, 145, 340, Decimal("0.0010")),
        ]
    ):
        record_ai_usage(
            db,
            tenant,
            provider="demo-local",
            model="kronflow-rag-v1",
            prompt_tokens=pt,
            completion_tokens=ct,
            latency_ms=lat,
            estimated_cost_usd=cost,
            is_simulation=False,
            agent_id=ag_sales["id"],
            agent_revision_id=ag_sales_pub.get("active_revision_id"),
            pricing_version="v1-demo",
            now=current - timedelta(hours=u_idx * 4 + 1),
        )

    return {
        "seeded": True,
        "already_populated": False,
        "counts": {
            "contacts": len(contacts),
            "leads": len(leads),
            "conversations": len(conv_ids),
            "opportunities": len(opportunities),
            "ai_proposals": 2,
            "agents": 2,
            "workflows": 2,
            "campaigns": 1,
            "webchat_widgets": 1,
            "privacy_requests": 1,
        },
    }
