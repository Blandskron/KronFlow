export type AgentChannel = 'whatsapp' | 'instagram' | 'facebook' | 'tiktok' | 'webchat' | 'email' | 'voice' | 'other';

export interface AgentMessageRequest {
  tenant_id?: string | null;
  channel: AgentChannel;
  conversation_id: string;
  customer: {
    external_id: string;
    name?: string | null;
    phone?: string | null;
    email?: string | null;
  };
  message: {
    type: 'text' | 'audio' | 'image' | 'file';
    content: string;
    attachments: Record<string, unknown>[];
  };
  metadata: {
    timestamp?: string | null;
    source_url?: string | null;
    campaign_id?: string | null;
    raw_payload: Record<string, unknown>;
  };
}

export interface AgentSource {
  source_id: string;
  document_id?: string | null;
  title: string;
  chunk_id?: string | null;
  score: number;
  page?: number | null;
  uri?: string | null;
}

export interface AgentMessageResponse {
  tenant_id: string;
  conversation_id: string;
  reply: {
    type: 'text';
    content: string;
  };
  actions: Array<{
    type: 'create_lead' | 'schedule_meeting' | 'send_email' | 'handoff_human' | 'create_ticket' | 'none';
    payload: Record<string, unknown>;
  }>;
  requires_human: boolean;
  confidence: number;
  sources: AgentSource[];
  next_step: 'continue_conversation' | 'wait_user' | 'handoff' | 'close';
}

export interface ContextDocumentPayload {
  title: string;
  filename: string;
  content: string;
  content_type: string;
  status: 'pending' | 'uploading' | 'received' | 'processing' | 'active' | 'rejected' | 'error' | 'draft' | 'deprecated';
  priority: number;
}

export interface DocumentRead {
  id: number;
  tenant_id: string;
  title: string;
  filename: string;
  content_type?: string;
  status: 'draft' | 'active' | 'deprecated';
  priority: number;
  version: number;
  source_type?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  error_message?: string | null;
}

export type BusinessContextAgentStatus = 'not_configured' | 'pending' | 'processing' | 'trained' | 'active' | 'error';

export interface BusinessContextStatus {
  progress_percent: number;
  agent_status: BusinessContextAgentStatus;
  last_updated_at: string | null;
  active_documents_count: number;
  documents: DocumentRead[];
  document_actions?: {
    delete?: boolean;
    patch?: boolean;
    replace?: boolean;
    retry_processing?: boolean;
  };
}

export interface TemplateRead {
  id: number;
  code: string;
  name: string;
  description: string;
  fields: Array<{ name: string; label?: string; hint?: string }>;
  download_options: Array<{
    format: 'docx' | 'pdf';
    template_id: number;
    filename: string;
    media_type: string;
  }>;
}

export interface SetupSessionRead {
  session_id: string;
  next_question: string;
}

export interface GeneratedContextRead {
  summary: string;
}

export interface RuleRead {
  id: number;
  tenant_id: string;
  name: string;
  rule_type: string;
  content: string;
  priority: number;
  is_active: boolean;
}

export interface RuleCreate {
  name: string;
  rule_type: string;
  content: string;
  priority?: number;
  is_active?: boolean;
}

export interface RulePatch {
  name?: string;
  rule_type?: string;
  content?: string;
  priority?: number;
  is_active?: boolean;
}

export interface RetrievalTrace {
  id: number;
  tenant_id: string;
  conversation_id: number | null;
  query: string;
  sources: any[];
  confidence: number;
  created_at?: string;
}
