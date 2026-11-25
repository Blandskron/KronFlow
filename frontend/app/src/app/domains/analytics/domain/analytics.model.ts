export interface AnalyticsSummary {
  total_leads: number;
  cold_leads: number;
  warm_leads: number;
  hot_leads: number;
  open_conversations: number;
  requires_human: number;
  messages_today: number;
  messages_last_7_days: number;
}

export interface ActivityFilters {
  start_date: string;
  end_date: string;
  time_zone: string;
}

export interface ActivityCounts {
  contacts_created: number;
  leads_created: number;
  inbound_messages: number;
  outbound_messages: number;
}

export interface AnalyticsActivity extends ActivityFilters {
  as_of: string;
  partial_day: string | null;
  totals: ActivityCounts;
  days: Array<ActivityCounts & { day: string }>;
}
