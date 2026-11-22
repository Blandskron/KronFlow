export interface Lead {
  id: number;
  full_name: string;
  phone: string;
  email: string;
  source: string;
  direction: 'inbound' | 'outbound' | string;
  temperature: 'cold' | 'warm' | 'hot' | string;
  lifecycle_status: string;
  assigned_to_user_id: number | null;
  score: number;
  tags: string[];
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export const leadStages = [
  { id: 'nuevo', label: 'Nuevo' },
  { id: 'contactado', label: 'Contactado' },
  { id: 'en_proceso', label: 'En proceso' },
  { id: 'ganado', label: 'Ganado' },
  { id: 'perdido', label: 'Perdido' }
] as const;
