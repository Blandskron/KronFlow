export type WorkflowNodeType = 'trigger' | 'condition' | 'wait' | 'action' | 'end';
export type WorkflowEdgeWhen = 'always' | 'true' | 'false';

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  label: string;
  config: Record<string, unknown>;
}

export interface WorkflowEdge {
  source: string;
  target: string;
  when: WorkflowEdgeWhen;
}

export interface WorkflowGraph {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
}

export interface WorkflowDefinitionItem {
  id: number;
  name: string;
  description: string;
  status: string;
  trigger_event_type: string;
  draft_graph: WorkflowGraph;
  draft_version: number;
  active_revision_id: number | null;
  active_revision_number: number | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRevisionItem {
  id: number;
  workflow_id: number;
  revision_number: number;
  status: string;
  trigger_event_type: string;
  graph_json: WorkflowGraph;
  publish_note: string | null;
  published_by: string | null;
  published_at: string;
}

export interface WorkflowValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  node_count: number;
  edge_count: number;
}

export interface WorkflowSimulationResult {
  valid: boolean;
  errors: string[];
  visited_nodes: string[];
  matched_branches: string[];
  discarded_branches: string[];
  planned_effects: Array<{ node_id: string; action_kind: string; config: Record<string, unknown> }>;
  would_wait_seconds: number;
}

export interface WorkflowStepRunItem {
  id: number;
  run_id: number;
  node_id: string;
  node_type: string;
  visit_number: number;
  status: string;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  effect_ref: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface WorkflowRunItem {
  id: number;
  workflow_id: number;
  revision_id: number;
  trigger_event_id: string;
  entity_type: string;
  entity_id: string;
  contact_id: number | null;
  conversation_id: number | null;
  status: string;
  current_node_id: string | null;
  wake_at: string | null;
  cancel_on_events: string[];
  context_json: Record<string, unknown>;
  error_message: string | null;
  started_at: string;
  updated_at: string;
  finished_at: string | null;
  steps: WorkflowStepRunItem[];
}

export interface WorkflowTemplateItem {
  code: string;
  name: string;
  description: string;
  trigger_event_type: string;
  graph: WorkflowGraph;
}
