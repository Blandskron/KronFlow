"""Governed tool registry, declarative JSON Schema validation, quota, and idempotent invocations."""

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.schemas.tool_hub import ToolCreateIn, ToolUpdateIn
from app.services.ai_extensions_service import enqueue_external_notification
from app.services.ai_proposal_service import create_ai_proposal
from app.services.domain_event_service import publish_domain_event_in_tx
from app.services.post_v1_service import simulate_appointment_slot
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.operations import Cliente
from app.tenant_models.phase4_hub import ToolDefinition, ToolInvocation


TOOL_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,78}$")

BUILTIN_TOOLS: tuple[dict[str, Any], ...] = (
    {
        "tool_key": "crm.contact.lookup",
        "name": "Consultar contacto CRM",
        "description": "Busca información básica de un contacto por ID, teléfono WhatsApp o correo.",
        "effect_mode": "read_only",
        "input_schema": {
            "type": "object",
            "required": [],
            "properties": {
                "client_id": {"type": "integer"},
                "whatsapp_id": {"type": "string", "maxLength": 64},
                "email": {"type": "string", "maxLength": 180},
            },
        },
        "connector_ref": "operational.crm",
        "max_calls_per_hour": 600,
    },
    {
        "tool_key": "scheduling.check_slot",
        "name": "Comprobar disponibilidad de agenda",
        "description": "Verifica si un recurso calendario tiene conflictos en un bloque horario.",
        "effect_mode": "read_only",
        "input_schema": {
            "type": "object",
            "required": ["resource_key", "starts_at", "ends_at"],
            "properties": {
                "resource_key": {"type": "string", "maxLength": 80},
                "starts_at": {"type": "string", "maxLength": 64},
                "ends_at": {"type": "string", "maxLength": 64},
            },
        },
        "connector_ref": "operational.scheduling",
        "max_calls_per_hour": 300,
    },
    {
        "tool_key": "crm.contact.rename",
        "name": "Proponer cambio de nombre de contacto",
        "description": "Crea una propuesta tipada pendiente de aprobación para renombrar un contacto.",
        "effect_mode": "proposal_required",
        "input_schema": {
            "type": "object",
            "required": ["resource_id", "name"],
            "properties": {
                "resource_id": {"type": "integer"},
                "name": {"type": "string", "maxLength": 160},
                "rationale": {"type": "string", "maxLength": 240},
            },
        },
        "connector_ref": "operational.proposals",
        "max_calls_per_hour": 120,
    },
    {
        "tool_key": "crm.lead.update_stage",
        "name": "Proponer cambio de etapa de lead",
        "description": "Crea una propuesta tipada para actualizar la etapa comercial del lead.",
        "effect_mode": "proposal_required",
        "input_schema": {
            "type": "object",
            "required": ["resource_id", "stage"],
            "properties": {
                "resource_id": {"type": "integer"},
                "stage": {
                    "type": "string",
                    "enum": ["nuevo", "contactado", "en_proceso", "ganado", "perdido"],
                },
                "rationale": {"type": "string", "maxLength": 240},
            },
        },
        "connector_ref": "operational.proposals",
        "max_calls_per_hour": 120,
    },
    {
        "tool_key": "crm.opportunity.add_note",
        "name": "Proponer nota en oportunidad",
        "description": "Crea una propuesta tipada para añadir una nota auditada a una oportunidad.",
        "effect_mode": "proposal_required",
        "input_schema": {
            "type": "object",
            "required": ["resource_id", "note"],
            "properties": {
                "resource_id": {"type": "integer"},
                "note": {"type": "string", "maxLength": 2000},
                "rationale": {"type": "string", "maxLength": 240},
            },
        },
        "connector_ref": "operational.proposals",
        "max_calls_per_hour": 120,
    },
    {
        "tool_key": "crm.conversation.request_handoff",
        "name": "Proponer derivación a humano",
        "description": "Solicita transición HITL a espera de operador humano.",
        "effect_mode": "proposal_required",
        "input_schema": {
            "type": "object",
            "required": ["resource_id", "reason"],
            "properties": {
                "resource_id": {"type": "integer"},
                "reason": {"type": "string", "maxLength": 180},
                "rationale": {"type": "string", "maxLength": 240},
            },
        },
        "connector_ref": "operational.proposals",
        "max_calls_per_hour": 120,
    },
    {
        "tool_key": "notification.send",
        "name": "Enviar notificación externa vía Outbox",
        "description": "Encola de forma durable e idempotente una notificación email o webhook_stub.",
        "effect_mode": "outbox_async",
        "input_schema": {
            "type": "object",
            "required": ["channel", "recipient", "event_type"],
            "properties": {
                "channel": {"type": "string", "enum": ["email", "webhook_stub"]},
                "recipient": {"type": "string", "maxLength": 255},
                "event_type": {"type": "string", "maxLength": 64},
                "payload": {"type": "object"},
            },
        },
        "connector_ref": "operational.outbox",
        "max_calls_per_hour": 120,
    },
)


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Tool timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def tools_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    return {ToolDefinition.__tablename__, ToolInvocation.__tablename__}.issubset(existing)


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not tools_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Tool hub schema is unavailable")


def _tool_to_dict(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "id": tool.id,
        "tool_key": tool.tool_key,
        "name": tool.name,
        "description": tool.description,
        "effect_mode": tool.effect_mode,
        "schema_version": tool.schema_version,
        "input_schema": dict(tool.input_schema or {}),
        "required_permission": tool.required_permission,
        "connector_ref": tool.connector_ref,
        "is_enabled": tool.is_enabled,
        "max_calls_per_hour": tool.max_calls_per_hour,
        "created_by": tool.created_by,
        "created_at": tool.created_at,
        "updated_at": tool.updated_at,
    }


def _invocation_to_dict(inv: ToolInvocation, *, duplicate: bool = False) -> dict[str, Any]:
    return {
        "id": inv.id,
        "tool_id": inv.tool_id,
        "tool_key": inv.tool_key,
        "schema_version": inv.schema_version,
        "idempotency_key": inv.idempotency_key,
        "arguments_json": dict(inv.arguments_json or {}),
        "effect_mode": inv.effect_mode,
        "status": inv.status,
        "result_json": dict(inv.result_json or {}),
        "proposal_id": inv.proposal_id,
        "outbox_job_id": inv.outbox_job_id,
        "invoked_by": inv.invoked_by,
        "correlation_id": inv.correlation_id,
        "created_at": inv.created_at,
        "duplicate": duplicate,
    }


def validate_arguments_against_schema(arguments: dict[str, Any], schema: dict[str, Any]) -> None:
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail="Tool arguments must be a JSON object")
    required = schema.get("required") or []
    for key in required:
        if key not in arguments or arguments[key] is None:
            raise HTTPException(status_code=422, detail=f"Missing required tool argument '{key}'")

    properties = schema.get("properties") or {}
    for key, val in arguments.items():
        spec = properties.get(key)
        if spec is None or val is None:
            continue
        expected_type = spec.get("type")
        if expected_type == "string":
            if not isinstance(val, str):
                raise HTTPException(status_code=422, detail=f"Argument '{key}' must be a string")
            max_len = spec.get("maxLength")
            if isinstance(max_len, int) and len(val) > max_len:
                raise HTTPException(status_code=422, detail=f"Argument '{key}' exceeds maxLength {max_len}")
        elif expected_type == "integer":
            if type(val) is not int:
                raise HTTPException(status_code=422, detail=f"Argument '{key}' must be an integer")
        elif expected_type == "number":
            if type(val) not in (int, float):
                raise HTTPException(status_code=422, detail=f"Argument '{key}' must be a number")
        elif expected_type == "boolean":
            if type(val) is not bool:
                raise HTTPException(status_code=422, detail=f"Argument '{key}' must be a boolean")
        elif expected_type == "object":
            if not isinstance(val, dict):
                raise HTTPException(status_code=422, detail=f"Argument '{key}' must be an object")
        elif expected_type == "array":
            if not isinstance(val, list):
                raise HTTPException(status_code=422, detail=f"Argument '{key}' must be an array")

        enum_vals = spec.get("enum")
        if isinstance(enum_vals, list) and val not in enum_vals:
            raise HTTPException(status_code=422, detail=f"Argument '{key}' must be one of {enum_vals}")


def ensure_builtin_tools(db: Session, tenant: TenantContext, *, now: datetime | None = None) -> None:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    for item in BUILTIN_TOOLS:
        db.execute(
            insert(ToolDefinition)
            .values(
                tool_key=item["tool_key"],
                name=item["name"],
                description=item["description"],
                effect_mode=item["effect_mode"],
                schema_version=1,
                input_schema=item["input_schema"],
                required_permission="crm.manage",
                connector_ref=item.get("connector_ref"),
                is_enabled=True,
                max_calls_per_hour=item["max_calls_per_hour"],
                created_by="system",
                created_at=current,
                updated_at=current,
            )
            .on_conflict_do_nothing(index_elements=["tool_key"])
        )
    db.commit()


def list_tools(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    ensure_builtin_tools(db, tenant)
    rows = list(db.scalars(select(ToolDefinition).order_by(ToolDefinition.id.asc())).all())
    return [_tool_to_dict(row) for row in rows]


def create_tool(
    db: Session,
    tenant: TenantContext,
    payload: ToolCreateIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_key = payload.tool_key.strip().lower()
    if not TOOL_KEY_RE.fullmatch(clean_key):
        raise HTTPException(status_code=422, detail="Invalid tool_key format")
    ensure_builtin_tools(db, tenant, now=now)
    if db.scalar(select(ToolDefinition.id).where(ToolDefinition.tool_key == clean_key)) is not None:
        raise HTTPException(status_code=409, detail=f"Tool '{clean_key}' already exists")
    current = _now(now)
    tool = ToolDefinition(
        tool_key=clean_key,
        name=payload.name.strip()[:160],
        description=payload.description.strip()[:400],
        effect_mode=payload.effect_mode,
        schema_version=1,
        input_schema=dict(payload.input_schema or {}),
        required_permission=payload.required_permission.strip()[:64],
        connector_ref=payload.connector_ref.strip()[:80] if payload.connector_ref else None,
        is_enabled=bool(payload.is_enabled),
        max_calls_per_hour=payload.max_calls_per_hour,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(tool)
    db.commit()
    db.refresh(tool)
    return _tool_to_dict(tool)


def update_tool(
    db: Session,
    tenant: TenantContext,
    tool_id: int,
    payload: ToolUpdateIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    ensure_builtin_tools(db, tenant, now=now)
    current = _now(now)
    tool = db.scalar(select(ToolDefinition).where(ToolDefinition.id == tool_id).with_for_update())
    if tool is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Tool not found")

    bump_version = False
    if payload.name is not None:
        tool.name = payload.name.strip()[:160]
    if payload.description is not None:
        tool.description = payload.description.strip()[:400]
    if payload.effect_mode is not None and payload.effect_mode != tool.effect_mode:
        tool.effect_mode = payload.effect_mode
        bump_version = True
    if payload.input_schema is not None and payload.input_schema != tool.input_schema:
        tool.input_schema = dict(payload.input_schema)
        bump_version = True
    if payload.required_permission is not None:
        tool.required_permission = payload.required_permission.strip()[:64]
    if payload.connector_ref is not None:
        tool.connector_ref = payload.connector_ref.strip()[:80] or None
    if payload.is_enabled is not None:
        tool.is_enabled = bool(payload.is_enabled)
    if payload.max_calls_per_hour is not None:
        tool.max_calls_per_hour = payload.max_calls_per_hour
    if bump_version:
        tool.schema_version += 1
    tool.updated_at = current
    db.commit()
    db.refresh(tool)
    return _tool_to_dict(tool)


def list_tool_invocations(
    db: Session,
    tenant: TenantContext,
    *,
    tool_key: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    stmt = select(ToolInvocation).order_by(ToolInvocation.id.desc()).limit(max(1, min(limit, 100)))
    if tool_key:
        stmt = stmt.where(ToolInvocation.tool_key == tool_key.strip().lower())
    rows = list(db.scalars(stmt).all())
    return [_invocation_to_dict(row) for row in rows]


def _execute_read_only(db: Session, tenant: TenantContext, tool_key: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool_key == "crm.contact.lookup":
        bind_tenant_session(db, tenant.schema_name)
        stmt = select(Cliente)
        if isinstance(arguments.get("client_id"), int):
            stmt = stmt.where(Cliente.id == arguments["client_id"])
        elif isinstance(arguments.get("whatsapp_id"), str) and arguments["whatsapp_id"].strip():
            stmt = stmt.where(Cliente.whatsapp_id == arguments["whatsapp_id"].strip())
        elif isinstance(arguments.get("email"), str) and arguments["email"].strip():
            stmt = stmt.where(Cliente.email == arguments["email"].strip().lower())
        else:
            raise HTTPException(status_code=422, detail="Provide client_id, whatsapp_id, or email for lookup")
        c = db.scalar(stmt.limit(1))
        if c is None:
            return {"found": False, "contact": None}
        return {
            "found": True,
            "contact": {
                "id": c.id,
                "name": c.nombre,
                "email": c.email,
                "whatsapp_id": c.whatsapp_id,
                "consent": c.consentimiento_datos,
            },
        }

    if tool_key == "scheduling.check_slot":
        try:
            starts_at = datetime.fromisoformat(str(arguments["starts_at"]))
            ends_at = datetime.fromisoformat(str(arguments["ends_at"]))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="starts_at and ends_at must be ISO-8601 datetimes") from exc
        return simulate_appointment_slot(
            db,
            tenant,
            resource_key=str(arguments["resource_key"]),
            starts_at=starts_at,
            ends_at=ends_at,
        )

    return {"ok": True, "echo": arguments}


def invoke_tool(
    db: Session,
    tenant: TenantContext,
    *,
    tool_key: str,
    arguments: dict[str, Any],
    idempotency_key: str,
    actor_user_id: str,
    expected_schema_version: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    clean_key = tool_key.strip().lower()
    clean_idem = idempotency_key.strip()
    if not clean_idem or len(clean_idem) > 180:
        raise HTTPException(status_code=422, detail="idempotency_key must be 1..180 characters")

    current = _now(now)
    ensure_builtin_tools(db, tenant, now=current)
    tool = db.scalar(select(ToolDefinition).where(ToolDefinition.tool_key == clean_key))
    if tool is None:
        raise HTTPException(status_code=404, detail=f"Tool '{clean_key}' not found")
    if not tool.is_enabled:
        raise HTTPException(status_code=403, detail=f"Tool '{clean_key}' is disabled")
    if expected_schema_version is not None and tool.schema_version != expected_schema_version:
        raise HTTPException(status_code=409, detail="Stale tool schema version")

    validate_arguments_against_schema(arguments, dict(tool.input_schema or {}))
    args_hash = _canonical_hash(arguments)

    existing = db.scalar(
        select(ToolInvocation).where(
            ToolInvocation.tool_key == clean_key,
            ToolInvocation.idempotency_key == clean_idem,
        )
    )
    if existing is not None:
        if existing.arguments_hash != args_hash:
            raise HTTPException(status_code=409, detail="Tool idempotency key reused with different arguments")
        return _invocation_to_dict(existing, duplicate=True)

    window_start = current - timedelta(hours=1)
    recent_calls = int(
        db.scalar(
            select(func.count())
            .select_from(ToolInvocation)
            .where(ToolInvocation.tool_key == clean_key, ToolInvocation.created_at >= window_start)
        )
        or 0
    )
    if recent_calls >= tool.max_calls_per_hour:
        raise HTTPException(status_code=429, detail=f"Hourly quota exceeded for tool '{clean_key}'")

    status_value = "completed"
    result_json: dict[str, Any] = {}
    proposal_id: int | None = None
    outbox_job_id: int | None = None

    if tool.effect_mode == "read_only":
        result_json = _execute_read_only(db, tenant, clean_key, arguments)
        status_value = "completed"
    elif tool.effect_mode == "proposal_required":
        resource_id = arguments.get("resource_id")
        if type(resource_id) is not int or resource_id < 1:
            raise HTTPException(status_code=422, detail="proposal_required tools require integer 'resource_id' >= 1")
        prop_args = {k: v for k, v in arguments.items() if k not in ("resource_id", "rationale")}
        proposal = create_ai_proposal(
            db,
            tenant,
            action_type=clean_key,
            resource_id=resource_id,
            arguments=prop_args,
            idempotency_key=f"tool:{clean_key}:{clean_idem}",
            proposed_by=f"tool:{actor_user_id}",
            rationale=str(arguments.get("rationale") or f"Invocación gobernada de {clean_key}"),
            now=current,
        )
        proposal_id = proposal["id"]
        status_value = "proposed"
        result_json = {"proposal_id": proposal_id, "proposal_status": proposal["status"]}
    elif tool.effect_mode == "outbox_async":
        notif = enqueue_external_notification(
            db,
            tenant,
            dedup_key=f"tool:{clean_key}:{clean_idem}",
            event_type=str(arguments.get("event_type") or clean_key),
            channel=str(arguments.get("channel") or "webhook_stub"),
            recipient=str(arguments.get("recipient") or "ops@tenant.local"),
            payload=dict(arguments.get("payload") or {}),
            actor_user_id=actor_user_id,
            now=current,
        )
        outbox_job_id = notif["outbox_job_id"]
        status_value = "queued"
        result_json = {"notification_id": notif["id"], "outbox_job_id": outbox_job_id}
    else:
        raise HTTPException(status_code=422, detail=f"Unsupported tool effect_mode '{tool.effect_mode}'")

    bind_tenant_session(db, tenant.schema_name)
    inv = ToolInvocation(
        tool_id=tool.id,
        tool_key=clean_key,
        schema_version=tool.schema_version,
        idempotency_key=clean_idem,
        arguments_json=dict(arguments),
        arguments_hash=args_hash,
        effect_mode=tool.effect_mode,
        status=status_value,
        result_json=result_json,
        proposal_id=proposal_id,
        outbox_job_id=outbox_job_id,
        invoked_by=actor_user_id[:64],
        correlation_id=audit_correlation.get(),
        created_at=current,
    )
    db.add(inv)
    db.flush()
    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="tool.invoked",
        aggregate_type="tool_invocation",
        aggregate_id=inv.id,
        payload={
            "tool_key": clean_key,
            "effect_mode": tool.effect_mode,
            "status": status_value,
            "proposal_id": proposal_id,
            "outbox_job_id": outbox_job_id,
        },
        occurred_at=current,
    )
    create_system_event(
        db,
        "tool.invoked",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"tool_key": clean_key, "invocation_id": inv.id, "status": status_value, "actor": actor_user_id},
    )
    db.commit()
    db.refresh(inv)
    return _invocation_to_dict(inv, duplicate=False)
