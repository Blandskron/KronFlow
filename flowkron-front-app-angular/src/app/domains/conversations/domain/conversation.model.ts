export interface Conversation {
  id: number;
  lead_id: number;
  lead_name: string;
  lead_phone: string;
  channel: string;
  external_thread_id: string;
  status: string;
  requires_human: boolean;
  last_message_at: string | null;
  last_message: string | null;
  temperature: string | null;
  created_at: string;
  updated_at: string;
  no_leidos?: number;
}

export interface ConversationCursor {
  before_at: string;
  before_id: number;
}

export interface ConversationMessage {
  id: number;
  conversation_id: number;
  external_message_id: string;
  sender_type: string;
  body: string;
  raw_payload: Record<string, unknown>;
  sent_at: string;
  created_at: string;
  delivery_status?: 'unknown' | 'received' | 'sent' | 'failed' | 'delivered' | 'read';
  delivery_failure_reason?: 'provider_rejected' | 'account_restricted' | 'connection_invalid' | null;
}

export interface PendingReply {
  inbound_message_id: number;
  status: 'queued' | 'sending' | 'unknown' | 'not_sent';
}
