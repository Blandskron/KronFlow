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
}
