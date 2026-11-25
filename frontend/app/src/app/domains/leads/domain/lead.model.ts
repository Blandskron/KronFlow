export interface Lead {
  id: number;
  contact_id?: number | null;
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

export interface InitialLeadResult { lead: Lead; created: boolean; }

export interface LeadActivity {
  id: number;
  kind: 'created' | 'stage' | 'temperature';
  created_at: string;
  previous: string | null;
  value: string | null;
}

export const leadStages = [
  { id: 'nuevo', label: 'Nuevo' },
  { id: 'contactado', label: 'Contactado' },
  { id: 'en_proceso', label: 'En proceso' },
  { id: 'ganado', label: 'Ganado' },
  { id: 'perdido', label: 'Perdido' }
] as const;

export const leadTemperatures = [
  { id: 'cold', label: 'Frío' }, { id: 'warm', label: 'Tibio' }, { id: 'hot', label: 'Caliente' }
] as const;
