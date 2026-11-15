export interface AgentProfile {
  id: number;
  name: string;
  role: string;
  status: string;
  prompt_config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}
