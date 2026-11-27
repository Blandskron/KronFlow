from datetime import datetime
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


ACTIVE_TENANT_TABLE_NAMES = {
    "whatsapp_turns",
    "whatsapp_turn_jobs",
    "whatsapp_send_evidence",
    "whatsapp_consent_state",
    "action_outbox_jobs",
    "contact_consent_decisions",
    "contact_suppressions",
    "conversation_controls",
    "conversation_control_events",
    "tenant_ai_policies",
    "tenant_retention_policies",
    "tenant_subprocessor_approvals",
    "pipeline_stages",
    "opportunities",
    "opportunity_activities",
    "ai_action_proposals",
    "contact_points",
    "lead_captures",
    "domain_events",
    "domain_event_subscriptions",
    "tenant_channel_connections",
    "message_templates",
    "template_versions",
    "campaigns",
    "campaign_approvals",
    "campaign_recipients",
    "delivery_attempts",
    "channel_events",
    "conversation_memory_items",
    "contact_enrichment_candidates",
    "external_notification_deliveries",
    "ai_usage_records",
    "webhook_subscriptions",
    "webhook_deliveries",
    "private_attachments",
    "calendar_appointments",
    "agent_revisions",
    "agent_rules",
    "agent_execution_traces",
    "setup_chat_sessions",
    "workflow_definitions",
    "workflow_revisions",
    "workflow_runs",
    "workflow_step_runs",
    "tool_definitions",
    "tool_invocations",
    "webchat_sessions",
    "external_entity_mappings",
    "connector_sync_cursors",
    "commerce_orders",
    "commerce_payment_events",
    "voice_call_sessions",
    "voice_call_segments",
    "remote_mcp_servers",
    "mensajes_procesados",
    "clientes",
    "leads",
    "inventario_vehiculos",
    "solicitudes_derechos",
    "log_limpiezas",
    "conversaciones",
    "mensajes_dashboard",
    "ejecutivos",
    "reglas_negocio",
    "rate_limit",
    "conversaciones_resumen",
    "tenant_agent_profiles",
    "business_context_documents",
    "business_context_forms",
    "business_context_fields",
    "business_context_form_submissions",
    "document_chunks",
    "document_embeddings",
}


class MensajeProcesado(Base):
    __tablename__ = "mensajes_procesados"
    __table_args__ = (
        Index("idx_mensajes_procesados_message_id", "message_id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    message_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    procesado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Cliente(Base):
    __tablename__ = "clientes"
    __table_args__ = (
        CheckConstraint("tipo_cliente IN ('prospecto', 'activo', 'recurrente', 'perdido')", name="ck_clientes_tipo_cliente"),
        Index("idx_clientes_whatsapp_id", "whatsapp_id"),
        Index("idx_clientes_email", "email"),
        Index("idx_clientes_consentimiento", "consentimiento_datos", "fecha_consentimiento"),
        Index("idx_clientes_rut_blind_index", "rut_blind_index"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rut: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    rut_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    rut_blind_index: Mapped[str | None] = mapped_column(String(64), nullable=True)
    nombre: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefono: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo_cliente: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'prospecto'"))
    canal_origen: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'whatsapp_directo'"))
    consentimiento_datos: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fecha_consentimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    canal_consentimiento: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_politica: Mapped[str | None] = mapped_column(Text, nullable=True, server_default=text("'v1.0'"))
    processing_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    processing_restricted_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    leads = relationship("Lead", back_populates="cliente")


class Ejecutivo(Base):
    __tablename__ = "ejecutivos"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    whatsapp: Mapped[str] = mapped_column(String(20), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=True, server_default=text("true"))
    leads_asignados: Mapped[int] = mapped_column(Integer, nullable=True, server_default=text("0"))
    ultimo_asignado_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("score_lead BETWEEN 0 AND 115", name="ck_leads_score_lead"),
        CheckConstraint("clasificacion IN ('caliente', 'tibio', 'frio')", name="ck_leads_clasificacion"),
        CheckConstraint(
            "plazo_compra IN ('este_dia', 'esta_semana', 'este_mes', 'tres_meses', 'cotizando', 'explorando')",
            name="ck_leads_plazo_compra",
        ),
        CheckConstraint("estado IN ('nuevo', 'contactado', 'en_proceso', 'ganado', 'perdido')", name="ck_leads_estado"),
        Index("idx_leads_seguimiento", "estado_seguimiento", "creado_en", "ultimo_followup_at"),
        Index("idx_leads_cliente_id", "cliente_id"),
        Index("idx_leads_clasificacion", "clasificacion"),
        Index("idx_leads_estado", "estado"),
        Index("idx_leads_creado_en", text("creado_en DESC")),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("tenant.clientes.id", ondelete="CASCADE"), nullable=False)
    score_lead: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("0"))
    clasificacion: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'frio'"))
    plazo_compra: Mapped[str | None] = mapped_column(Text, nullable=True)
    requiere_credito: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    estado: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'nuevo'"))
    resumen_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_factors_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    human_review_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    human_review_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    followup_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("0"))
    ultimo_followup_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado_seguimiento: Mapped[str | None] = mapped_column(String(30), nullable=True, server_default=text("'pendiente'"))
    ejecutivo_id: Mapped[int | None] = mapped_column(ForeignKey("tenant.ejecutivos.id"), nullable=True)

    cliente = relationship("Cliente", back_populates="leads")
    ejecutivo = relationship("Ejecutivo")


class InventarioVehiculo(Base):
    __tablename__ = "inventario_vehiculos"
    __table_args__ = (
        CheckConstraint("condicion IN ('nuevo', 'usado', 'certificado')", name="ck_inventario_condicion"),
        CheckConstraint(
            "tipo_vehiculo IN ('sedan', 'suv', 'hatchback', 'pickup', 'coupe', 'furgon', 'station_wagon', 'otro')",
            name="ck_inventario_tipo_vehiculo",
        ),
        CheckConstraint("transmision IN ('manual', 'automatica', 'cvt', 'otro')", name="ck_inventario_transmision"),
        CheckConstraint("combustible IN ('bencina', 'diesel', 'hibrido', 'electrico', 'otro')", name="ck_inventario_combustible"),
        Index("idx_inventario_disponible", "disponible", postgresql_where=text("disponible = true")),
        Index("idx_inventario_marca_modelo", "marca", "modelo"),
        Index("idx_inventario_precio", "precio_lista"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    marca: Mapped[str] = mapped_column(Text, nullable=False)
    modelo: Mapped[str] = mapped_column(Text, nullable=False)
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    version: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str | None] = mapped_column(Text, nullable=True)
    condicion: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'nuevo'"))
    kilometraje: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    tipo_vehiculo: Mapped[str | None] = mapped_column(Text, nullable=True)
    transmision: Mapped[str | None] = mapped_column(Text, nullable=True)
    combustible: Mapped[str | None] = mapped_column(Text, nullable=True)
    precio_lista: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disponible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class SolicitudDerecho(Base):
    __tablename__ = "solicitudes_derechos"
    __table_args__ = (
        CheckConstraint(
            "tipo_derecho IN ('acceso', 'rectificacion', 'eliminacion', 'oposicion', 'portabilidad', 'bloqueo')",
            name="ck_solicitudes_tipo_derecho",
        ),
        CheckConstraint("estado IN ('pendiente', 'en_proceso', 'completada')", name="ck_solicitudes_estado"),
        Index("idx_solicitudes_whatsapp_id", "whatsapp_id"),
        Index("idx_solicitudes_estado", "estado", "fecha_limite"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    client_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    subject_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    whatsapp_id: Mapped[str] = mapped_column(Text, nullable=False)
    tipo_derecho: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'pendiente'"))
    fecha_solicitud: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    fecha_limite: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now() + interval '30 days'"))
    fecha_resolucion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)


class LogLimpieza(Base):
    __tablename__ = "log_limpiezas"
    __table_args__ = (
        CheckConstraint("estado IN ('exitoso', 'error')", name="ck_log_limpiezas_estado"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fecha_ejecucion: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    mensajes_eliminados: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    clientes_anonimizados: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    solicitudes_eliminadas: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    estado: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'exitoso'"))
    detalle: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    prev_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Conversation(Base):
    __tablename__ = "conversaciones"
    __table_args__ = (
        Index("idx_conversaciones_session_id", "session_id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[dict] = mapped_column(JSONB, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class Message(Base):
    __tablename__ = "mensajes_dashboard"
    __table_args__ = (
        CheckConstraint("rol IN ('usuario', 'agente')", name="ck_mensajes_dashboard_rol"),
        CheckConstraint("direction IN ('inbound', 'outbound')", name="ck_message_direction"),
        CheckConstraint("delivery_status IN ('unknown', 'received', 'sent', 'delivered', 'read', 'failed')", name="ck_message_delivery_status"),
        Index("uq_message_external_identity", "connection_id", "channel", "external_message_id", unique=True),
        Index("idx_message_provider_identity", "connection_id", "channel", "provider_message_id"),
        {"schema": "tenant"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    whatsapp_id: Mapped[str] = mapped_column(Text, nullable=False)
    rol: Mapped[str] = mapped_column(Text, nullable=False)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    connection_id: Mapped[str] = mapped_column(String(80), nullable=False, server_default=text("'default'"))
    channel: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'whatsapp'"))
    external_message_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(220), nullable=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'text'"))
    delivery_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'unknown'"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class ReglaNegocio(Base):
    __tablename__ = "reglas_negocio"
    __table_args__ = {"schema": "tenant"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tipo: Mapped[str] = mapped_column(String(30), nullable=False)
    alcance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    activo: Mapped[bool | None] = mapped_column(Boolean, nullable=True, server_default=text("true"))
    creado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)
    creado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, server_default=text("now()"))


class RateLimit(Base):
    __tablename__ = "rate_limit"
    __table_args__ = {"schema": "tenant"}

    whatsapp_id: Mapped[str] = mapped_column(String, primary_key=True)
    contador: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default=text("1"))
    ventana_inicio: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True, server_default=text("now()"))


class ConversacionResumen(Base):
    __tablename__ = "conversaciones_resumen"
    __table_args__ = (
        CheckConstraint("ultimo_rol IN ('usuario', 'agente')", name="ck_conversaciones_resumen_ultimo_rol"),
        Index("idx_conv_resumen_ultimo_mensaje", text("ultimo_mensaje_en DESC")),
        {"schema": "tenant"},
    )

    whatsapp_id: Mapped[str] = mapped_column(Text, primary_key=True)
    nombre_cliente: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultimo_mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultimo_rol: Mapped[str | None] = mapped_column(Text, nullable=True)
    ultimo_mensaje_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    total_mensajes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    no_leidos: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
