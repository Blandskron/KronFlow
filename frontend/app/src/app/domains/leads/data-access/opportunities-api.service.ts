import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';

export interface PipelineStage {
  id: number;
  slug: string;
  name: string;
  position: number;
  stage_kind: 'open' | 'won' | 'lost';
  is_active: boolean;
}

export interface OpportunityItem {
  id: number;
  contact_id: number;
  lead_id: number | null;
  conversation_id: number | null;
  stage_id: number;
  stage_slug: string;
  stage_name: string;
  stage_kind: 'open' | 'won' | 'lost';
  title: string;
  owner_user_id: string | null;
  amount: string | null;
  currency: string;
  outcome: 'open' | 'won' | 'lost';
  close_reason: string | null;
  version: number;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

@Injectable({ providedIn: 'root' })
export class OpportunitiesApiService {
  private readonly http = inject(HttpClient);

  listStages(): Observable<PipelineStage[]> {
    return this.http
      .get<ApiResponse<{ items: PipelineStage[] }>>(`${OPERATIONAL_API_BASE_URL}/opportunities/stages`)
      .pipe(map((r) => r.data.items));
  }

  list(filters: { stage_id?: number; outcome?: string; limit?: number; offset?: number } = {}): Observable<PaginatedResponse<OpportunityItem>> {
    return this.http
      .get<ApiResponse<PaginatedResponse<OpportunityItem>>>(`${OPERATIONAL_API_BASE_URL}/opportunities`, {
        params: toParams(filters)
      })
      .pipe(map((r) => r.data));
  }

  create(payload: {
    title: string;
    contact_id?: number;
    lead_id?: number;
    amount?: number;
    currency?: string;
  }): Observable<OpportunityItem> {
    return this.http
      .post<ApiResponse<OpportunityItem>>(`${OPERATIONAL_API_BASE_URL}/opportunities`, payload)
      .pipe(map((r) => r.data));
  }

  update(
    opportunityId: number,
    payload: { expected_version: number; stage_id?: number; outcome?: 'open' | 'won' | 'lost'; close_reason?: string; note?: string }
  ): Observable<OpportunityItem> {
    return this.http
      .patch<ApiResponse<OpportunityItem>>(`${OPERATIONAL_API_BASE_URL}/opportunities/${opportunityId}`, payload)
      .pipe(map((r) => r.data));
  }
}
