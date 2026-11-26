"""Pydantic schemas for declarative versioned workflows, compiler validation, simulation, and runs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WorkflowNodeIn(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: Literal["trigger", "condition", "wait", "action", "end"]
    label: str = Field(default="", max_length=120)
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdgeIn(BaseModel):
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    when: Literal["always", "true", "false"] = "always"


class WorkflowGraphIn(BaseModel):
    nodes: list[WorkflowNodeIn] = Field(default_factory=list, max_length=30)
    edges: list[WorkflowEdgeIn] = Field(default_factory=list, max_length=60)


class WorkflowCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=500)
    trigger_event_type: str = Field(min_length=1, max_length=80)
    graph: WorkflowGraphIn


class WorkflowDraftUpdateIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    status: Literal["draft", "active", "paused", "archived"] | None = None
    trigger_event_type: str | None = Field(default=None, min_length=1, max_length=80)
    graph: WorkflowGraphIn | None = None
    expected_version: int = Field(ge=1)


class WorkflowPublishIn(BaseModel):
    expected_version: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=240)


class WorkflowSimulateIn(BaseModel):
    sample_payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowValidationOut(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    node_count: int = 0
    edge_count: int = 0


class WorkflowSimulationOut(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    visited_nodes: list[str] = Field(default_factory=list)
    matched_branches: list[str] = Field(default_factory=list)
    discarded_branches: list[str] = Field(default_factory=list)
    planned_effects: list[dict[str, Any]] = Field(default_factory=list)
    would_wait_seconds: int = 0


class WorkflowRevisionOut(BaseModel):
    id: int
    workflow_id: int
    revision_number: int
    status: str
    trigger_event_type: str
    graph_json: dict[str, Any]
    publish_note: str | None = None
    published_by: str | None = None
    published_at: datetime


class WorkflowOut(BaseModel):
    id: int
    name: str
    description: str
    status: str
    trigger_event_type: str
    draft_graph: dict[str, Any]
    draft_version: int
    active_revision_id: int | None = None
    active_revision_number: int | None = None
    created_by: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowStepRunOut(BaseModel):
    id: int
    run_id: int
    node_id: str
    node_type: str
    visit_number: int
    status: str
    input_json: dict[str, Any]
    output_json: dict[str, Any]
    effect_ref: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime | None = None


class WorkflowRunOut(BaseModel):
    id: int
    workflow_id: int
    revision_id: int
    trigger_event_id: str
    entity_type: str
    entity_id: str
    contact_id: int | None = None
    conversation_id: int | None = None
    status: str
    current_node_id: str | None = None
    wake_at: datetime | None = None
    cancel_on_events: list[str] = Field(default_factory=list)
    context_json: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    steps: list[WorkflowStepRunOut] = Field(default_factory=list)


class WorkflowTemplateOut(BaseModel):
    code: str
    name: str
    description: str
    trigger_event_type: str
    graph: WorkflowGraphIn
