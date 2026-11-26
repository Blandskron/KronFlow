import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';
import { ActivityFilters, AnalyticsActivity, AnalyticsSummary } from '../domain/analytics.model';

export interface AnalyticsKpis {
  as_of: string;
  pipeline: {
    open_opportunities: number;
    won_opportunities: number;
    lost_opportunities: number;
    won_amount_by_currency: Record<string, string>;
    win_rate: number | null;
  };
  campaigns: {
    total_campaigns: number;
    recipients_accepted: number;
    recipients_delivered: number;
    recipients_suppressed: number;
    delivery_rate: number | null;
  };
  events: {
    total_domain_events: number;
    last_event_id: number;
  };
  governance: {
    open_privacy_cases: number;
    pending_ai_proposals: number;
    executed_ai_proposals: number;
  };
  ai_usage?: {
    days: number;
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_cost_usd: string;
    avg_latency_ms: number;
  };
  workflows?: {
    active_workflows: number;
    runs_running: number;
    runs_waiting: number;
    runs_completed: number;
    runs_failed: number;
    runs_cancelled: number;
  };
  commerce?: {
    total_orders: number;
    paid_orders: number;
    discrepancy_orders: number;
    confirmed_gross_by_currency: Record<string, number>;
    refunded_by_currency: Record<string, number>;
    confirmed_net_by_currency: Record<string, number>;
  };
  voice?: {
    total_calls: number;
    completed_calls: number;
    transferred_calls: number;
    no_answer_calls: number;
    total_billable_seconds: number;
    total_estimated_cost_usd: string;
  };
}

@Injectable({ providedIn: 'root' })
export class AnalyticsApiService {
  private readonly http = inject(HttpClient);

  analyticsSummary(): Observable<AnalyticsSummary> {
    return this.http
      .get<ApiResponse<AnalyticsSummary>>(`${OPERATIONAL_API_BASE_URL}/analytics/summary`)
      .pipe(map((response) => response.data));
  }

  activity(filters: ActivityFilters): Observable<AnalyticsActivity> {
    return this.http.get<ApiResponse<AnalyticsActivity>>(`${OPERATIONAL_API_BASE_URL}/analytics/activity`, {
      params: toParams({ ...filters })
    }).pipe(map(({ data }) => data));
  }

  kpis(): Observable<AnalyticsKpis> {
    return this.http
      .get<ApiResponse<AnalyticsKpis>>(`${OPERATIONAL_API_BASE_URL}/analytics/kpis`)
      .pipe(map(({ data }) => data));
  }
}
