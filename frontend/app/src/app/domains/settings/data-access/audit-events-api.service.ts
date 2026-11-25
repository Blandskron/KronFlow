import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';
import { map } from 'rxjs';

export interface AuditEvent {
  event_id: string;
  event_type: string;
  occurred_at: string;
  correlation_id: string;
  data: Record<string, string | number>;
}

export interface AuditEventPage { items: AuditEvent[]; next_before_id: number | null; }

export interface AuditEventFilters { event_type: string; correlation_id: string; before_id?: number; }

@Injectable({ providedIn: 'root' })
export class AuditEventsApiService {
  private readonly http = inject(HttpClient);

  list(filters: AuditEventFilters) {
    return this.http.get<ApiResponse<AuditEventPage>>(`${OPERATIONAL_API_BASE_URL}/operational/audit-events`, {
      params: toParams({ ...filters })
    }).pipe(map(({ data }) => data));
  }
}
