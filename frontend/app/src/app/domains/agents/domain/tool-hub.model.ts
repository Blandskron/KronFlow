export type ToolEffectMode = 'read_only' | 'proposal_required' | 'outbox_async';

export interface ToolDefinitionItem {
  id: number;
  tool_key: string;
  name: string;
  description: string;
  effect_mode: ToolEffectMode | string;
  schema_version: number;
  input_schema: Record<string, unknown>;
  required_permission: string;
  connector_ref: string | null;
  is_enabled: boolean;
  max_calls_per_hour: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ToolInvocationItem {
  id: number;
  tool_id: number;
  tool_key: string;
  schema_version: number;
  idempotency_key: string;
  arguments_json: Record<string, unknown>;
  effect_mode: string;
  status: string;
  result_json: Record<string, unknown>;
  proposal_id: number | null;
  outbox_job_id: number | null;
  invoked_by: string;
  correlation_id: string | null;
  created_at: string;
  duplicate?: boolean;
}

export interface WebchatWidgetItem {
  id: number;
  widget_key: string;
  name: string;
  is_active: boolean;
  allowed_origins: string[];
  agent_id: number | null;
  welcome_message: string;
  session_ttl_minutes: number;
  rate_limit_per_minute: number;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChannelWebhookRouteItem {
  id: number;
  channel: 'whatsapp' | 'instagram' | 'messenger' | string;
  provider: string;
  external_account_id: string;
  connection_id: number | null;
  secret_fingerprint: string;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExternalMappingItem {
  id: number;
  connection_ref: string;
  resource_type: string;
  remote_id: string;
  local_type: string;
  local_id: string;
  remote_version: string | null;
  local_version: number;
  sync_state: 'synced' | 'conflict' | 'disconnected' | string;
  conflict_payload: Record<string, unknown>;
  owner_user_id: string | null;
  last_synced_at: string;
  created_at: string;
  updated_at: string;
}

export interface RemoteMcpServerItem {
  id: number;
  server_key: string;
  name: string;
  base_url: string;
  auth_header_name: string;
  auth_fingerprint: string | null;
  allowed_tools: string[];
  discovered_tools: Record<string, unknown>[];
  is_active: boolean;
  revoked_at: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface CommerceOrderItem {
  id: number;
  provider: 'mercadopago' | 'shopify' | 'stub' | string;
  external_order_id: string | null;
  order_number: string;
  client_id: number | null;
  opportunity_id: number | null;
  conversation_id: number | null;
  currency: string;
  expected_amount_minor: number;
  confirmed_amount_minor: number;
  refunded_amount_minor: number;
  net_confirmed_minor: number;
  status: string;
  checkout_url: string | null;
  discrepancy_reason: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface VoiceCallItem {
  id: number;
  provider: string;
  external_call_id: string;
  direction: 'inbound' | 'outbound' | string;
  from_number: string;
  to_number: string;
  client_id: number | null;
  conversation_id: number | null;
  status: string;
  billable_seconds: number;
  estimated_cost_usd: string;
  recording_consent: boolean;
  barge_in_count: number;
  close_reason: string | null;
  started_at: string;
  ended_at: string | null;
}
