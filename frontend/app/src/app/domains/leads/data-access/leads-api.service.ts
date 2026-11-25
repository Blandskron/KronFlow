import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { InitialLeadResult, Lead, LeadActivity } from '../domain/lead.model';
import { toParams } from '@shared/utils/http.utils';

@Injectable({ providedIn: 'root' })
export class LeadsApiService {
  private readonly http = inject(HttpClient);

  listLeads(filters: {
    temperature?: string;
    lifecycle_status?: string;
    direction?: string;
    limit?: number;
    offset?: number;
    q?: string;
    contact_id?: number;
    status_group?: 'open' | 'closed';
  } = {}): Observable<PaginatedResponse<Lead>> {
    return this.http
      .get<ApiResponse<PaginatedResponse<Lead>>>(`${OPERATIONAL_API_BASE_URL}/leads`, {
        params: toParams(filters)
      })
      .pipe(map((response) => response.data));
  }

  updateStage(lead: Lead, stage: string) {
    return this.update(lead, { lifecycle_status: stage });
  }

  get(id: string) {
    return this.http.get<ApiResponse<Lead>>(`${OPERATIONAL_API_BASE_URL}/leads/${encodeURIComponent(id)}`)
      .pipe(map(({ data }) => data));
  }

  activity(id: number) {
    return this.http.get<ApiResponse<LeadActivity[]>>(`${OPERATIONAL_API_BASE_URL}/leads/${id}/activity`)
      .pipe(map(({ data }) => data));
  }

  start(contactId: number) {
    return this.http.post<ApiResponse<InitialLeadResult>>(`${OPERATIONAL_API_BASE_URL}/contacts/${contactId}/lead`, null)
      .pipe(map(({ data }) => data));
  }

  update(lead: Lead, changes: { lifecycle_status?: string; temperature?: string }) {
    return this.http.patch<ApiResponse<Lead>>(`${OPERATIONAL_API_BASE_URL}/leads/${lead.id}`, {
      ...changes, expected_updated_at: lead.updated_at
    }).pipe(map(({ data }) => data));
  }
}
