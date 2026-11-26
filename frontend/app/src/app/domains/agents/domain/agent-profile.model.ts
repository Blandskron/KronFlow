export interface AgentRevision {
  id: number;
  agent_id: number;
  revision_number: number;
  status: string;
  name: string;
  role: string;
  tone: string;
  language: string;
  instructions: string;
  allowed_tools: string[];
  allowed_document_ids: number[];
  limits: Record<string, unknown>;
  prompt_config: Record<string, unknown>;
  publish_note: string | null;
  published_by: string | null;
  published_at: string;
}

export interface AgentProfile {
  id: number;
  name: string;
  role: string;
  status: string;
  tone: string;
  language: string;
  instructions: string;
  allowed_tools: string[];
  allowed_document_ids: number[];
  limits: Record<string, unknown>;
  prompt_config: Record<string, unknown>;
  is_default: boolean;
  version: number;
  active_revision_id: number | null;
  active_revision_number: number | null;
  created_at: string;
  updated_at: string;
}

export interface AgentConfigurePayload {
  name: string;
  role: string;
  tone?: string;
  language?: string;
  instructions?: string;
  allowed_tools?: string[];
  allowed_document_ids?: number[];
  limits?: Record<string, unknown>;
  prompt_config?: Record<string, unknown>;
  is_default?: boolean;
}

export interface AgentUpdatePayload {
  name?: string;
  role?: string;
  status?: 'draft' | 'active' | 'archived';
  tone?: string;
  language?: string;
  instructions?: string;
  allowed_tools?: string[];
  allowed_document_ids?: number[];
  limits?: Record<string, unknown>;
  prompt_config?: Record<string, unknown>;
  is_default?: boolean;
  expected_version?: number;
}
