"""Declarative versioned workflow compiler, dry-run simulator, event-driven engine, and wait cancellation."""

from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import inspect, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.contracts import audit_correlation
from app.core.tenant_resolver import TenantContext
from app.schemas.workflow import WorkflowCreateIn, WorkflowDraftUpdateIn, WorkflowGraphIn
from app.services.action_outbox_service import enqueue_outbox_action
from app.services.ai_proposal_service import ACTION_RESOURCE_MAP, _canonical_hash, _validate_typed_arguments
from app.services.domain_event_service import domain_events_ready, publish_domain_event_in_tx
from app.services.tenant_data import bind_tenant_session
from app.services.tenant_provisioning_service import create_system_event
from app.tenant_models.ai_extensions import ExternalNotificationDelivery
from app.tenant_models.ai_proposal import AIActionProposal
from app.tenant_models.conversation_control import ConversationControl, ConversationControlEvent
from app.tenant_models.domain_events import DomainEvent, DomainEventSubscription
from app.tenant_models.operations import Cliente, Conversation, Lead
from app.tenant_models.opportunity import Opportunity, OpportunityActivity
from app.tenant_models.workflows import WorkflowDefinition, WorkflowRevision, WorkflowRun, WorkflowStepRun


SUPPORTED_TRIGGER_EVENTS = frozenset(
    {
        "lead.created",
        "lead.captured",
        "lead.stage.changed",
        "lead.temperature.changed",
        "opportunity.created",
        "opportunity.stage.changed",
        "opportunity.won",
        "opportunity.lost",
        "conversation.handoff.requested",
        "message.inbound.received",
        "campaign.approved",
        "ai.proposal.executed",
    }
)
SUPPORTED_WORKFLOW_ACTIONS = frozenset(
    {
        "proposal.create",
        "notification.send",
        "lead.update",
        "opportunity.add_note",
        "conversation.request_handoff",
        "noop",
    }
)
SUPPORTED_CONDITION_OPERATORS = frozenset({"eq", "neq", "in", "contains", "gt", "lt", "exists"})
MAX_WORKFLOW_NODES = 30
MAX_WAIT_SECONDS = 30 * 24 * 3600
VALID_WORKFLOW_STATUSES = frozenset({"draft", "active", "paused", "archived"})
DEFAULT_CANCEL_EVENTS = ("message.inbound.received", "contact.suppressed", "consent.withdrawn")


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("Workflow timestamps must include a time zone")
    return now.astimezone(timezone.utc)


def workflows_ready(db: Session, tenant: TenantContext) -> bool:
    inspector = inspect(db.connection())
    existing = set(inspector.get_table_names(schema=tenant.schema_name))
    return {
        WorkflowDefinition.__tablename__,
        WorkflowRevision.__tablename__,
        WorkflowRun.__tablename__,
        WorkflowStepRun.__tablename__,
    }.issubset(existing)


def _require_ready(db: Session, tenant: TenantContext) -> None:
    if not workflows_ready(db, tenant):
        raise HTTPException(status_code=503, detail="Workflow engine schema is unavailable")


def list_workflow_templates() -> list[dict[str, Any]]:
    return [
        {
            "code": "lead-warmup-followup",
            "name": "Seguimiento automático a leads nuevos",
            "description": "Espera una ventana configurable tras el alta del lead y notifica si no respondió ni se dio de baja.",
            "trigger_event_type": "lead.created",
            "graph": {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "Lead creado", "config": {}},
                    {
                        "id": "w1",
                        "type": "wait",
                        "label": "Esperar respuesta 1h",
                        "config": {
                            "delay_seconds": 3600,
                            "cancel_on_events": list(DEFAULT_CANCEL_EVENTS),
                        },
                    },
                    {
                        "id": "a1",
                        "type": "action",
                        "label": "Notificar seguimiento",
                        "config": {
                            "action_kind": "notification.send",
                            "channel": "webhook_stub",
                            "recipient": "sales-followup",
                            "message": "Recordatorio automático de seguimiento al lead.",
                        },
                    },
                    {"id": "e1", "type": "end", "label": "Fin", "config": {}},
                ],
                "edges": [
                    {"source": "t1", "target": "w1", "when": "always"},
                    {"source": "w1", "target": "a1", "when": "always"},
                    {"source": "a1", "target": "e1", "when": "always"},
                ],
            },
        },
        {
            "code": "hot-lead-proposal",
            "name": "Calificación rápida de lead caliente",
            "description": "Evalúa temperatura caliente y propone actualización tipada de etapa sin omitir revisión humana.",
            "trigger_event_type": "lead.temperature.changed",
            "graph": {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "Cambio de temperatura", "config": {}},
                    {
                        "id": "c1",
                        "type": "condition",
                        "label": "¿Es caliente?",
                        "config": {"field": "temperature", "operator": "eq", "value": "hot"},
                    },
                    {
                        "id": "a1",
                        "type": "action",
                        "label": "Proponer avance de etapa",
                        "config": {
                            "action_kind": "proposal.create",
                            "action_type": "crm.lead.update_stage",
                            "arguments": {"stage": "en_proceso"},
                            "rationale": "Lead clasificado caliente por evento de dominio.",
                        },
                    },
                    {"id": "e1", "type": "end", "label": "Fin", "config": {}},
                ],
                "edges": [
                    {"source": "t1", "target": "c1", "when": "always"},
                    {"source": "c1", "target": "a1", "when": "true"},
                    {"source": "c1", "target": "e1", "when": "false"},
                    {"source": "a1", "target": "e1", "when": "always"},
                ],
            },
        },
        {
            "code": "opportunity-won-note",
            "name": "Nota de cierre al ganar oportunidad",
            "description": "Registra automáticamente una nota de cierre y notificación interna cuando una oportunidad se gana.",
            "trigger_event_type": "opportunity.won",
            "graph": {
                "nodes": [
                    {"id": "t1", "type": "trigger", "label": "Oportunidad ganada", "config": {}},
                    {
                        "id": "a1",
                        "type": "action",
                        "label": "Registrar nota de cierre",
                        "config": {
                            "action_kind": "opportunity.add_note",
                            "note": "Cierre ganado registrado por automatización.",
                        },
                    },
                    {"id": "e1", "type": "end", "label": "Fin", "config": {}},
                ],
                "edges": [
                    {"source": "t1", "target": "a1", "when": "always"},
                    {"source": "a1", "target": "e1", "when": "always"},
                ],
            },
        },
    ]


def _validate_node_config(node: Any, errors: list[str], warnings: list[str], outgoing_edges: list[Any]) -> None:
    cfg = node.config or {}
    if node.type == "condition":
        field = cfg.get("field")
        op = cfg.get("operator")
        if not isinstance(field, str) or not field.strip():
            errors.append(f"Condition node '{node.id}' requires non-empty config.field")
        if not isinstance(op, str) or op not in SUPPORTED_CONDITION_OPERATORS:
            errors.append(f"Condition node '{node.id}' has invalid operator '{op}'")
        if op != "exists" and "value" not in cfg:
            errors.append(f"Condition node '{node.id}' requires config.value for operator '{op}'")
        when_set = {e.when for e in outgoing_edges}
        if not when_set.intersection({"true", "always"}):
            warnings.append(f"Condition node '{node.id}' has no 'true' branch")
        if not when_set.intersection({"false", "always"}):
            warnings.append(f"Condition node '{node.id}' has no 'false' branch")
    elif node.type == "wait":
        delay = cfg.get("delay_seconds")
        if type(delay) is not int or not 1 <= delay <= MAX_WAIT_SECONDS:
            errors.append(f"Wait node '{node.id}' requires integer delay_seconds in 1..{MAX_WAIT_SECONDS}")
        cancel_events = cfg.get("cancel_on_events")
        if cancel_events is not None and (
            not isinstance(cancel_events, list) or not all(isinstance(item, str) and item.strip() for item in cancel_events)
        ):
            errors.append(f"Wait node '{node.id}' cancel_on_events must be a list of event names")
    elif node.type == "action":
        action_kind = cfg.get("action_kind")
        if not isinstance(action_kind, str) or action_kind not in SUPPORTED_WORKFLOW_ACTIONS:
            errors.append(f"Action node '{node.id}' unsupported action_kind '{action_kind}'")
        elif action_kind == "proposal.create":
            action_type = cfg.get("action_type")
            if action_type not in ACTION_RESOURCE_MAP:
                errors.append(f"Action node '{node.id}' requires valid action_type for proposal.create")


def validate_workflow_graph(trigger_event_type: str, graph: WorkflowGraphIn | dict[str, Any]) -> dict[str, Any]:
    parsed = graph if isinstance(graph, WorkflowGraphIn) else WorkflowGraphIn.model_validate(graph)
    errors: list[str] = []
    warnings: list[str] = []

    if trigger_event_type not in SUPPORTED_TRIGGER_EVENTS:
        errors.append(f"Unsupported trigger_event_type '{trigger_event_type}'")

    nodes = parsed.nodes
    edges = parsed.edges
    if not nodes:
        errors.append("Workflow graph must contain at least one node")
        return {"valid": False, "errors": errors, "warnings": warnings, "node_count": 0, "edge_count": len(edges)}
    if len(nodes) > MAX_WORKFLOW_NODES:
        errors.append(f"Workflow graph cannot exceed {MAX_WORKFLOW_NODES} nodes")

    node_map: dict[str, Any] = {}
    for node in nodes:
        if node.id in node_map:
            errors.append(f"Duplicate node id '{node.id}'")
        node_map[node.id] = node

    triggers = [node for node in nodes if node.type == "trigger"]
    if len(triggers) != 1:
        errors.append(f"Workflow graph must contain exactly one trigger node (found {len(triggers)})")

    adj: dict[str, list[Any]] = {node.id: [] for node in nodes}
    in_degree: dict[str, int] = {node.id: 0 for node in nodes}
    for edge in edges:
        if edge.source == edge.target:
            errors.append(f"Self-loop edge on '{edge.source}' is not allowed")
            continue
        if edge.source not in node_map or edge.target not in node_map:
            errors.append(f"Edge '{edge.source}' -> '{edge.target}' references unknown node")
            continue
        adj[edge.source].append(edge)
        in_degree[edge.target] += 1

    if len(triggers) == 1 and in_degree.get(triggers[0].id, 0) > 0:
        errors.append(f"Trigger node '{triggers[0].id}' cannot have incoming edges")

    for node in nodes:
        _validate_node_config(node, errors, warnings, adj.get(node.id, []))

    # Kahn topological check guarantees acyclic DAG (no unbounded loops).
    temp_in = dict(in_degree)
    topo_q = deque([nid for nid, deg in temp_in.items() if deg == 0])
    visited_topo = 0
    while topo_q:
        curr = topo_q.popleft()
        visited_topo += 1
        for edge in adj.get(curr, []):
            temp_in[edge.target] -= 1
            if temp_in[edge.target] == 0:
                topo_q.append(edge.target)
    if visited_topo < len(node_map):
        errors.append("Workflow graph contains a cycle; unbounded loops are not allowed in v1")

    # BFS reachability from trigger node detects orphan nodes.
    if len(triggers) == 1 and not any("Trigger" in err for err in errors):
        reachable: set[str] = set()
        bfs_q = deque([triggers[0].id])
        while bfs_q:
            curr = bfs_q.popleft()
            if curr in reachable:
                continue
            reachable.add(curr)
            for edge in adj.get(curr, []):
                if edge.target not in reachable:
                    bfs_q.append(edge.target)
        orphans = [nid for nid in node_map if nid not in reachable]
        if orphans:
            errors.append(f"Unreachable nodes from trigger: {', '.join(sorted(orphans))}")

        for nid in reachable:
            if not adj.get(nid) and node_map[nid].type != "end":
                warnings.append(f"Terminal node '{nid}' is not of type 'end'")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }


def _resolve_field_value(context: dict[str, Any], field_path: str) -> Any:
    parts = [part for part in field_path.split(".") if part]
    if not parts:
        return None
    for root in (context, context.get("payload") if isinstance(context.get("payload"), dict) else None):
        if root is None:
            continue
        curr: Any = root
        found = True
        for part in parts:
            if isinstance(curr, dict) and part in curr:
                curr = curr[part]
            else:
                found = False
                break
        if found:
            return curr
    return None


def _evaluate_condition(config: dict[str, Any], context: dict[str, Any]) -> bool:
    field = str(config.get("field") or "")
    op = str(config.get("operator") or "eq")
    expected = config.get("value")
    actual = _resolve_field_value(context, field)
    if op == "exists":
        return actual is not None
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "in":
        return isinstance(expected, list) and actual in expected
    if op == "contains":
        if isinstance(actual, str) and isinstance(expected, str):
            return expected.lower() in actual.lower()
        if isinstance(actual, list):
            return expected in actual
        return False
    if op in ("gt", "lt"):
        try:
            a_num = float(actual)
            e_num = float(expected)
        except (TypeError, ValueError):
            return False
        return a_num > e_num if op == "gt" else a_num < e_num
    return False


def _select_next_edge(outgoing: list[dict[str, Any]], *, condition_result: bool | None = None) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not outgoing:
        return None, []
    if condition_result is None:
        chosen = next((e for e in outgoing if e.get("when") == "always"), outgoing[0])
        discarded = [e for e in outgoing if e is not chosen]
        return chosen, discarded
    want = "true" if condition_result else "false"
    chosen = next((e for e in outgoing if e.get("when") == want), None)
    if chosen is None:
        chosen = next((e for e in outgoing if e.get("when") == "always"), None)
    discarded = [e for e in outgoing if e is not chosen]
    return chosen, discarded


def _revision_to_dict(rev: WorkflowRevision) -> dict[str, Any]:
    return {
        "id": rev.id,
        "workflow_id": rev.workflow_id,
        "revision_number": rev.revision_number,
        "status": rev.status,
        "trigger_event_type": rev.trigger_event_type,
        "graph_json": dict(rev.graph_json or {}),
        "publish_note": rev.publish_note,
        "published_by": rev.published_by,
        "published_at": rev.published_at,
    }


def _workflow_to_dict(db: Session, wf: WorkflowDefinition) -> dict[str, Any]:
    active_rev_num = None
    if wf.active_revision_id is not None:
        rev = db.get(WorkflowRevision, wf.active_revision_id)
        if rev is not None:
            active_rev_num = rev.revision_number
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "status": wf.status,
        "trigger_event_type": wf.trigger_event_type,
        "draft_graph": dict(wf.draft_graph or {}),
        "draft_version": wf.draft_version,
        "active_revision_id": wf.active_revision_id,
        "active_revision_number": active_rev_num,
        "created_by": wf.created_by,
        "created_at": wf.created_at,
        "updated_at": wf.updated_at,
    }


def _step_to_dict(step: WorkflowStepRun) -> dict[str, Any]:
    return {
        "id": step.id,
        "run_id": step.run_id,
        "node_id": step.node_id,
        "node_type": step.node_type,
        "visit_number": step.visit_number,
        "status": step.status,
        "input_json": dict(step.input_json or {}),
        "output_json": dict(step.output_json or {}),
        "effect_ref": step.effect_ref,
        "error_message": step.error_message,
        "started_at": step.started_at,
        "finished_at": step.finished_at,
    }


def _run_to_dict(run: WorkflowRun, steps: list[WorkflowStepRun] | None = None) -> dict[str, Any]:
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "revision_id": run.revision_id,
        "trigger_event_id": run.trigger_event_id,
        "entity_type": run.entity_type,
        "entity_id": run.entity_id,
        "contact_id": run.contact_id,
        "conversation_id": run.conversation_id,
        "status": run.status,
        "current_node_id": run.current_node_id,
        "wake_at": run.wake_at,
        "cancel_on_events": list(run.cancel_on_events or []),
        "context_json": dict(run.context_json or {}),
        "error_message": run.error_message,
        "started_at": run.started_at,
        "updated_at": run.updated_at,
        "finished_at": run.finished_at,
        "steps": [_step_to_dict(s) for s in (steps or [])],
    }


def list_workflows(db: Session, tenant: TenantContext) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    rows = list(db.scalars(select(WorkflowDefinition).order_by(WorkflowDefinition.id.asc())).all())
    return [_workflow_to_dict(db, row) for row in rows]


def get_workflow(db: Session, tenant: TenantContext, workflow_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    wf = db.get(WorkflowDefinition, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return _workflow_to_dict(db, wf)


def create_workflow(
    db: Session,
    tenant: TenantContext,
    payload: WorkflowCreateIn,
    *,
    actor_user_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    if payload.trigger_event_type not in SUPPORTED_TRIGGER_EVENTS:
        raise HTTPException(status_code=422, detail=f"Unsupported trigger_event_type '{payload.trigger_event_type}'")
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    wf = WorkflowDefinition(
        name=payload.name.strip()[:160],
        description=payload.description.strip()[:500],
        status="draft",
        trigger_event_type=payload.trigger_event_type.strip()[:80],
        draft_graph=payload.graph.model_dump(),
        draft_version=1,
        created_by=actor_user_id[:64] if actor_user_id else None,
        created_at=current,
        updated_at=current,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return _workflow_to_dict(db, wf)


def update_workflow_draft(
    db: Session,
    tenant: TenantContext,
    workflow_id: int,
    payload: WorkflowDraftUpdateIn,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    wf = db.scalar(select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_id).with_for_update())
    if wf is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.draft_version != payload.expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale workflow draft version")

    if payload.trigger_event_type is not None:
        if payload.trigger_event_type not in SUPPORTED_TRIGGER_EVENTS:
            db.rollback()
            raise HTTPException(status_code=422, detail=f"Unsupported trigger_event_type '{payload.trigger_event_type}'")
        wf.trigger_event_type = payload.trigger_event_type.strip()[:80]
    if payload.name is not None:
        wf.name = payload.name.strip()[:160]
    if payload.description is not None:
        wf.description = payload.description.strip()[:500]
    if payload.status is not None:
        if payload.status not in VALID_WORKFLOW_STATUSES:
            db.rollback()
            raise HTTPException(status_code=422, detail="Invalid workflow status")
        if payload.status == "active" and wf.active_revision_id is None:
            db.rollback()
            raise HTTPException(status_code=422, detail="Publish a validated revision before setting workflow active")
        wf.status = payload.status
    if payload.graph is not None:
        wf.draft_graph = payload.graph.model_dump()

    wf.draft_version += 1
    wf.updated_at = current
    db.commit()
    db.refresh(wf)
    return _workflow_to_dict(db, wf)


def validate_saved_workflow(db: Session, tenant: TenantContext, workflow_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    wf = db.get(WorkflowDefinition, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return validate_workflow_graph(wf.trigger_event_type, wf.draft_graph or {})


def simulate_workflow(
    db: Session,
    tenant: TenantContext,
    workflow_id: int,
    sample_payload: dict[str, Any],
) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    wf = db.get(WorkflowDefinition, workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    validation = validate_workflow_graph(wf.trigger_event_type, wf.draft_graph or {})
    if not validation["valid"]:
        return {
            "valid": False,
            "errors": validation["errors"],
            "visited_nodes": [],
            "matched_branches": [],
            "discarded_branches": [],
            "planned_effects": [],
            "would_wait_seconds": 0,
        }

    graph = wf.draft_graph or {}
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    adj: dict[str, list[dict[str, Any]]] = {nid: [] for nid in nodes}
    for edge in graph.get("edges", []):
        adj[edge["source"]].append(edge)

    curr_id: str | None = next((n["id"] for n in nodes.values() if n["type"] == "trigger"), None)
    visited_nodes: list[str] = []
    matched_branches: list[str] = []
    discarded_branches: list[str] = []
    planned_effects: list[dict[str, Any]] = []
    would_wait_seconds = 0
    guard = 0

    while curr_id and guard <= MAX_WORKFLOW_NODES:
        guard += 1
        node = nodes[curr_id]
        visited_nodes.append(curr_id)
        cfg = node.get("config") or {}
        cond_res: bool | None = None
        if node["type"] == "condition":
            cond_res = _evaluate_condition(cfg, {"payload": sample_payload, **sample_payload})
        elif node["type"] == "wait":
            would_wait_seconds += int(cfg.get("delay_seconds") or 0)
        elif node["type"] == "action":
            planned_effects.append(
                {
                    "node_id": curr_id,
                    "action_kind": cfg.get("action_kind"),
                    "config": cfg,
                }
            )
        elif node["type"] == "end":
            break

        chosen, discarded = _select_next_edge(adj.get(curr_id, []), condition_result=cond_res)
        for edge in discarded:
            discarded_branches.append(f"{edge['source']}->{edge['target']}({edge.get('when', 'always')})")
        if chosen is None:
            break
        matched_branches.append(f"{chosen['source']}->{chosen['target']}({chosen.get('when', 'always')})")
        curr_id = chosen["target"]

    return {
        "valid": True,
        "errors": [],
        "visited_nodes": visited_nodes,
        "matched_branches": matched_branches,
        "discarded_branches": discarded_branches,
        "planned_effects": planned_effects,
        "would_wait_seconds": would_wait_seconds,
    }


def publish_workflow(
    db: Session,
    tenant: TenantContext,
    workflow_id: int,
    *,
    expected_version: int,
    actor_user_id: str | None = None,
    note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)

    wf = db.scalar(select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_id).with_for_update())
    if wf is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Workflow not found")
    if wf.draft_version != expected_version:
        db.rollback()
        raise HTTPException(status_code=409, detail="Stale workflow draft version")

    validation = validate_workflow_graph(wf.trigger_event_type, wf.draft_graph or {})
    if not validation["valid"]:
        db.rollback()
        raise HTTPException(status_code=422, detail={"message": "Workflow validation failed", "errors": validation["errors"]})

    latest_rev = db.scalar(
        select(WorkflowRevision.revision_number)
        .where(WorkflowRevision.workflow_id == wf.id)
        .order_by(WorkflowRevision.revision_number.desc())
        .limit(1)
    )
    next_rev_num = int(latest_rev or 0) + 1

    db.execute(
        update(WorkflowRevision)
        .where(WorkflowRevision.workflow_id == wf.id, WorkflowRevision.status == "active")
        .values(status="superseded")
    )

    rev = WorkflowRevision(
        workflow_id=wf.id,
        revision_number=next_rev_num,
        status="active",
        trigger_event_type=wf.trigger_event_type,
        graph_json=dict(wf.draft_graph or {}),
        publish_note=note.strip()[:240] if note else None,
        published_by=actor_user_id[:64] if actor_user_id else None,
        published_at=current,
    )
    db.add(rev)
    db.flush()

    wf.active_revision_id = rev.id
    wf.status = "active"
    wf.draft_version += 1
    wf.updated_at = current

    publish_domain_event_in_tx(
        db,
        tenant,
        event_type="workflow.published",
        aggregate_type="workflow",
        aggregate_id=wf.id,
        payload={"workflow_id": wf.id, "revision_id": rev.id, "revision_number": rev.revision_number},
        occurred_at=current,
    )
    create_system_event(
        db,
        "workflow.published",
        tenant.auth_tenant_id,
        tenant.schema_name,
        {"workflow_id": wf.id, "revision_id": rev.id, "revision_number": rev.revision_number, "actor_user_id": actor_user_id},
    )
    db.commit()
    db.refresh(rev)
    return _revision_to_dict(rev)


def list_workflow_revisions(db: Session, tenant: TenantContext, workflow_id: int) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    if db.get(WorkflowDefinition, workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    rows = list(
        db.scalars(
            select(WorkflowRevision)
            .where(WorkflowRevision.workflow_id == workflow_id)
            .order_by(WorkflowRevision.revision_number.desc())
        ).all()
    )
    return [_revision_to_dict(row) for row in rows]


def list_workflow_runs(
    db: Session,
    tenant: TenantContext,
    *,
    workflow_id: int | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    stmt = select(WorkflowRun).order_by(WorkflowRun.id.desc()).limit(max(1, min(limit, 100)))
    if workflow_id is not None:
        stmt = stmt.where(WorkflowRun.workflow_id == workflow_id)
    if status_filter:
        stmt = stmt.where(WorkflowRun.status == status_filter.strip())
    runs = list(db.scalars(stmt).all())
    if not runs:
        return []
    run_ids = [r.id for r in runs]
    steps = list(
        db.scalars(
            select(WorkflowStepRun)
            .where(WorkflowStepRun.run_id.in_(run_ids))
            .order_by(WorkflowStepRun.id.asc())
        ).all()
    )
    steps_by_run: dict[int, list[WorkflowStepRun]] = {}
    for s in steps:
        steps_by_run.setdefault(s.run_id, []).append(s)
    return [_run_to_dict(r, steps_by_run.get(r.id, [])) for r in runs]


def get_workflow_run(db: Session, tenant: TenantContext, run_id: int) -> dict[str, Any]:
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    run = db.get(WorkflowRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    steps = list(
        db.scalars(
            select(WorkflowStepRun)
            .where(WorkflowStepRun.run_id == run.id)
            .order_by(WorkflowStepRun.id.asc())
        ).all()
    )
    return _run_to_dict(run, steps)


def cancel_workflow_run(
    db: Session,
    tenant: TenantContext,
    run_id: int,
    *,
    reason: str = "cancelled_by_operator",
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now(now)
    bind_tenant_session(db, tenant.schema_name)
    _require_ready(db, tenant)
    run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
    if run is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Workflow run not found")
    if run.status not in ("running", "waiting"):
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Cannot cancel workflow run in status '{run.status}'")

    run.status = "cancelled"
    run.wake_at = None
    run.error_message = reason.strip()[:300]
    run.updated_at = current
    run.finished_at = current
    db.execute(
        update(WorkflowStepRun)
        .where(WorkflowStepRun.run_id == run.id, WorkflowStepRun.status == "waiting")
        .values(status="cancelled", error_message=run.error_message, finished_at=current)
    )
    db.commit()
    return get_workflow_run(db, tenant, run.id)


def _resolve_event_refs_in_tx(db: Session, event: DomainEvent) -> tuple[int | None, int | None]:
    payload = event.payload or {}
    contact_id = payload.get("contact_id") or payload.get("client_id")
    conversation_id = payload.get("conversation_id")

    if event.aggregate_type == "lead":
        try:
            lead = db.get(Lead, int(event.aggregate_id))
            if lead is not None and contact_id is None:
                contact_id = lead.cliente_id
        except (TypeError, ValueError):
            pass
    elif event.aggregate_type == "opportunity":
        try:
            opp = db.get(Opportunity, int(event.aggregate_id))
            if opp is not None:
                contact_id = contact_id or opp.contact_id
                conversation_id = conversation_id or opp.conversation_id
        except (TypeError, ValueError):
            pass
    elif event.aggregate_type == "conversation":
        try:
            conv = db.get(Conversation, int(event.aggregate_id))
            if conv is not None:
                conversation_id = conversation_id or conv.id
                if contact_id is None and conv.session_id:
                    contact_id = db.scalar(select(Cliente.id).where(Cliente.whatsapp_id == conv.session_id))
        except (TypeError, ValueError):
            pass
    elif event.aggregate_type == "contact":
        try:
            contact_id = contact_id or int(event.aggregate_id)
        except (TypeError, ValueError):
            pass

    return (
        int(contact_id) if isinstance(contact_id, int) else None,
        int(conversation_id) if isinstance(conversation_id, int) else None,
    )


def _execute_action_in_tx(
    db: Session,
    tenant: TenantContext,
    run: WorkflowRun,
    node_id: str,
    visit_number: int,
    config: dict[str, Any],
    *,
    current: datetime,
) -> tuple[str | None, dict[str, Any]]:
    kind = str(config.get("action_kind") or "noop")
    idem_key = f"wf:{run.id}:{node_id}:{visit_number}"

    if kind == "noop":
        return None, {"action_kind": "noop"}

    if kind == "notification.send":
        channel = str(config.get("channel") or "webhook_stub")
        if channel not in ("email", "webhook_stub"):
            channel = "webhook_stub"
        recipient = str(config.get("recipient") or "workflow@tenant.local")[:255]
        notif_payload = {
            "workflow_id": run.workflow_id,
            "run_id": run.id,
            "entity_type": run.entity_type,
            "entity_id": run.entity_id,
            "message": config.get("message") or "",
        }
        job, _ = enqueue_outbox_action(
            db,
            tenant,
            action_type="notification.external.send",
            idempotency_key=f"notif:{idem_key}",
            payload={
                "event_type": f"workflow.{run.workflow_id}",
                "channel": channel,
                "recipient": recipient,
                "payload": notif_payload,
            },
            available_at=current,
            commit=False,
        )
        inspector = inspect(db.connection())
        if inspector.has_table(ExternalNotificationDelivery.__tablename__, schema=tenant.schema_name):
            delivery = ExternalNotificationDelivery(
                dedup_key=idem_key[:180],
                event_type=f"workflow.{run.workflow_id}"[:64],
                channel=channel,
                recipient=recipient,
                payload=notif_payload,
                status="queued",
                outbox_job_id=job.id,
                created_by=f"workflow:{run.workflow_id}",
                created_at=current,
                updated_at=current,
            )
            db.add(delivery)
            db.flush()
        return f"outbox:{job.id}", {"action_kind": kind, "outbox_job_id": job.id, "channel": channel}

    if kind == "proposal.create":
        action_type = str(config.get("action_type") or "")
        arguments = _validate_typed_arguments(action_type, dict(config.get("arguments") or {}))
        resource_type = ACTION_RESOURCE_MAP[action_type]
        resource_id = config.get("resource_id")
        if not isinstance(resource_id, int):
            if resource_type == "contact" and run.contact_id:
                resource_id = run.contact_id
            elif resource_type == "conversation" and run.conversation_id:
                resource_id = run.conversation_id
            elif run.entity_type == resource_type and run.entity_id.isdigit():
                resource_id = int(run.entity_id)
        if not isinstance(resource_id, int) or resource_id < 1:
            raise ValueError(f"Missing target {resource_type} ID for proposal.create")

        digest = _canonical_hash({"resource_id": resource_id, "arguments": arguments})
        inserted_id = db.scalar(
            insert(AIActionProposal)
            .values(
                action_type=action_type,
                resource_type=resource_type,
                resource_id=resource_id,
                arguments_json=arguments,
                arguments_hash=digest,
                idempotency_key=idem_key[:180],
                status="pending",
                proposal_version=1,
                proposed_by=f"workflow:{run.workflow_id}",
                rationale=str(config.get("rationale") or "Propuesta generada por workflow")[:240],
                correlation_id=audit_correlation.get(),
                expires_at=current + timedelta(minutes=60),
                created_at=current,
                updated_at=current,
            )
            .on_conflict_do_nothing(index_elements=["action_type", "idempotency_key"])
            .returning(AIActionProposal.id)
        )
        return (f"proposal:{inserted_id}" if inserted_id else None), {
            "action_kind": kind,
            "proposal_id": inserted_id,
            "action_type": action_type,
        }

    if kind == "lead.update":
        lead_id = int(run.entity_id) if run.entity_type == "lead" and run.entity_id.isdigit() else None
        if lead_id is not None:
            lead = db.get(Lead, lead_id)
            if lead is not None:
                if isinstance(config.get("stage"), str):
                    lead.estado = config["stage"].strip()[:40]
                if isinstance(config.get("temperature"), str):
                    temp_map = {"cold": "frio", "warm": "tibio", "hot": "caliente"}
                    lead.clasificacion = temp_map.get(config["temperature"].strip(), config["temperature"].strip())
                db.flush()
                return f"lead:{lead.id}", {"action_kind": kind, "lead_id": lead.id}
        return None, {"action_kind": kind, "skipped": "no_lead_target"}

    if kind == "opportunity.add_note":
        opp_id = int(run.entity_id) if run.entity_type == "opportunity" and run.entity_id.isdigit() else None
        note_text = str(config.get("note") or "Nota automática de workflow").strip()
        if opp_id is not None and db.get(Opportunity, opp_id) is not None:
            act = OpportunityActivity(
                opportunity_id=opp_id,
                activity_type="note_added",
                actor_user_id=f"workflow:{run.workflow_id}",
                note=note_text[:1000],
                metadata_json={"workflow_id": run.workflow_id, "run_id": run.id},
                created_at=current,
            )
            db.add(act)
            db.flush()
            return f"opportunity_activity:{act.id}", {"action_kind": kind, "opportunity_id": opp_id}
        return None, {"action_kind": kind, "skipped": "no_opportunity_target"}

    if kind == "conversation.request_handoff":
        if run.conversation_id is not None and db.get(Conversation, run.conversation_id) is not None:
            from app.services.conversation_control_service import mark_waiting_human_in_tx

            reason_text = str(config.get("reason") or "Derivación solicitada por workflow")[:180]
            mark_waiting_human_in_tx(
                db,
                tenant,
                run.conversation_id,
                actor_user_id=f"workflow:{run.workflow_id}",
                reason=reason_text,
                now=current,
            )
            return f"conversation:{run.conversation_id}", {"action_kind": kind, "conversation_id": run.conversation_id}
        return None, {"action_kind": kind, "skipped": "no_conversation_target"}

    raise ValueError(f"Unsupported workflow action '{kind}'")


def _advance_run_in_tx(
    db: Session,
    tenant: TenantContext,
    run: WorkflowRun,
    graph: dict[str, Any],
    *,
    current: datetime,
    resuming_from_wait: bool = False,
) -> str:
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    adj: dict[str, list[dict[str, Any]]] = {nid: [] for nid in nodes}
    for edge in graph.get("edges", []):
        if edge["source"] in adj:
            adj[edge["source"]].append(edge)

    curr_id = run.current_node_id
    if resuming_from_wait and curr_id and curr_id in nodes:
        db.execute(
            update(WorkflowStepRun)
            .where(WorkflowStepRun.run_id == run.id, WorkflowStepRun.node_id == curr_id, WorkflowStepRun.status == "waiting")
            .values(status="completed", finished_at=current)
        )
        chosen, _ = _select_next_edge(adj.get(curr_id, []))
        curr_id = chosen["target"] if chosen else None
        run.status = "running"
        run.wake_at = None

    guard = 0
    while curr_id and guard <= MAX_WORKFLOW_NODES:
        guard += 1
        node = nodes.get(curr_id)
        if node is None:
            run.status = "failed"
            run.error_message = f"Missing node '{curr_id}'"
            run.updated_at = current
            run.finished_at = current
            return "failed"

        cfg = node.get("config") or {}
        run.current_node_id = curr_id
        run.updated_at = current

        if node["type"] == "wait":
            delay = int(cfg.get("delay_seconds") or 60)
            wake_at = current + timedelta(seconds=delay)
            cancel_events = list(cfg.get("cancel_on_events") or DEFAULT_CANCEL_EVENTS)
            step = WorkflowStepRun(
                run_id=run.id,
                node_id=curr_id,
                node_type="wait",
                visit_number=1,
                status="waiting",
                input_json={"delay_seconds": delay},
                output_json={"wake_at": wake_at.isoformat()},
                started_at=current,
            )
            db.add(step)
            run.status = "waiting"
            run.wake_at = wake_at
            run.cancel_on_events = cancel_events
            db.flush()
            return "waiting"

        cond_res: bool | None = None
        output: dict[str, Any] = {}
        effect_ref: str | None = None
        try:
            if node["type"] == "condition":
                cond_res = _evaluate_condition(cfg, run.context_json or {})
                output = {"matched": cond_res}
            elif node["type"] == "action":
                effect_ref, output = _execute_action_in_tx(
                    db, tenant, run, curr_id, 1, cfg, current=current,
                )
            elif node["type"] == "end":
                output = {"done": True}
        except Exception as exc:
            step = WorkflowStepRun(
                run_id=run.id,
                node_id=curr_id,
                node_type=node["type"],
                visit_number=1,
                status="failed",
                input_json=dict(cfg),
                output_json={},
                error_message=str(exc)[:300],
                started_at=current,
                finished_at=current,
            )
            db.add(step)
            run.status = "failed"
            run.error_message = str(exc)[:300]
            run.finished_at = current
            db.flush()
            return "failed"

        db.add(
            WorkflowStepRun(
                run_id=run.id,
                node_id=curr_id,
                node_type=node["type"],
                visit_number=1,
                status="completed",
                input_json=dict(cfg),
                output_json=output,
                effect_ref=effect_ref,
                started_at=current,
                finished_at=current,
            )
        )
        if node["type"] == "end":
            break
        chosen, _ = _select_next_edge(adj.get(curr_id, []), condition_result=cond_res)
        curr_id = chosen["target"] if chosen else None

    run.status = "completed"
    run.wake_at = None
    run.updated_at = current
    run.finished_at = current
    db.flush()
    return "completed"


def process_tenant_workflows(
    db: Session,
    tenant: TenantContext,
    *,
    now: datetime | None = None,
    limit: int = 50,
) -> dict[str, int]:
    """Consume new domain events for published workflows and resume due waiting runs."""
    summary = {
        "events_processed": 0,
        "runs_started": 0,
        "runs_resumed": 0,
        "runs_completed": 0,
        "runs_waiting": 0,
        "runs_failed": 0,
    }
    bind_tenant_session(db, tenant.schema_name)
    if not workflows_ready(db, tenant) or not domain_events_ready(db, tenant):
        return summary

    current = _now(now)
    sub_name = "workflow_engine"
    db.execute(
        insert(DomainEventSubscription)
        .values(
            subscriber_name=sub_name,
            event_types=[],
            last_event_id=0,
            is_active=True,
            updated_at=current,
        )
        .on_conflict_do_nothing(index_elements=["subscriber_name"])
    )
    sub = db.scalar(
        select(DomainEventSubscription)
        .where(DomainEventSubscription.subscriber_name == sub_name)
        .with_for_update()
    )
    if sub is None or not sub.is_active:
        db.commit()
        return summary

    active_rows = db.execute(
        select(WorkflowDefinition, WorkflowRevision)
        .join(WorkflowRevision, WorkflowDefinition.active_revision_id == WorkflowRevision.id)
        .where(WorkflowDefinition.status == "active")
    ).all()
    by_trigger: dict[str, list[tuple[WorkflowDefinition, WorkflowRevision]]] = {}
    for wf, rev in active_rows:
        by_trigger.setdefault(rev.trigger_event_type, []).append((wf, rev))

    events = list(
        db.scalars(
            select(DomainEvent)
            .where(DomainEvent.id > sub.last_event_id)
            .order_by(DomainEvent.id.asc())
            .limit(max(1, min(limit, 100)))
        ).all()
    )
    max_event_id = sub.last_event_id
    for event in events:
        summary["events_processed"] += 1
        max_event_id = max(max_event_id, event.id)
        matches = by_trigger.get(event.event_type, [])
        if not matches:
            continue
        contact_id, conversation_id = _resolve_event_refs_in_tx(db, event)
        for wf, rev in matches:
            existing_run_id = db.scalar(
                select(WorkflowRun.id).where(
                    WorkflowRun.revision_id == rev.id,
                    WorkflowRun.trigger_event_id == event.event_id,
                    WorkflowRun.entity_id == event.aggregate_id,
                )
            )
            if existing_run_id is not None:
                continue
            graph = dict(rev.graph_json or {})
            trigger_node = next((n["id"] for n in graph.get("nodes", []) if n.get("type") == "trigger"), None)
            run = WorkflowRun(
                workflow_id=wf.id,
                revision_id=rev.id,
                trigger_event_id=event.event_id,
                entity_type=event.aggregate_type,
                entity_id=event.aggregate_id,
                contact_id=contact_id,
                conversation_id=conversation_id,
                status="running",
                current_node_id=trigger_node,
                context_json={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": event.aggregate_id,
                    "payload": dict(event.payload or {}),
                },
                started_at=current,
                updated_at=current,
            )
            db.add(run)
            db.flush()
            summary["runs_started"] += 1
            outcome = _advance_run_in_tx(db, tenant, run, graph, current=current)
            summary[f"runs_{outcome}"] = summary.get(f"runs_{outcome}", 0) + 1

    if max_event_id > sub.last_event_id:
        sub.last_event_id = max_event_id
        sub.updated_at = current

    # Resume any waiting runs whose scheduled wake_at has arrived.
    due_runs = list(
        db.scalars(
            select(WorkflowRun)
            .where(WorkflowRun.status == "waiting", WorkflowRun.wake_at.isnot(None), WorkflowRun.wake_at <= current)
            .order_by(WorkflowRun.wake_at.asc(), WorkflowRun.id.asc())
            .limit(max(1, min(limit, 100)))
            .with_for_update(skip_locked=True)
        ).all()
    )
    for run in due_runs:
        rev = db.get(WorkflowRevision, run.revision_id)
        if rev is None:
            run.status = "failed"
            run.error_message = "Revision missing on resume"
            run.finished_at = current
            summary["runs_failed"] += 1
            continue
        summary["runs_resumed"] += 1
        outcome = _advance_run_in_tx(
            db, tenant, run, dict(rev.graph_json or {}), current=current, resuming_from_wait=True,
        )
        summary[f"runs_{outcome}"] = summary.get(f"runs_{outcome}", 0) + 1

    db.commit()
    return summary
