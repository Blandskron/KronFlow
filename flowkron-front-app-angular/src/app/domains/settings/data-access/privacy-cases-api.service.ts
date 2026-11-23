import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';
import { map } from 'rxjs';

export type PrivacyState = 'pendiente' | 'en_proceso' | 'completada';

export interface PrivacyCase {
  id: number;
  kind: string;
  state: PrivacyState;
  requested_at: string;
  due_at: string;
  completed_at: string | null;
}

@Injectable({ providedIn: 'root' })
export class PrivacyCasesApiService {
  private readonly http = inject(HttpClient);
  private readonly url = `${OPERATIONAL_API_BASE_URL}/operational/privacy-cases`;

  list(state: string, offset: number) {
    return this.http.get<ApiResponse<PaginatedResponse<PrivacyCase>>>(this.url, {
      params: toParams({ state, limit: 25, offset })
    }).pipe(map(({ data }) => data));
  }

  transition(entry: PrivacyCase, state: 'en_proceso' | 'completada', confirmed: boolean) {
    return this.http.patch<ApiResponse<PrivacyCase>>(`${this.url}/${entry.id}`, {
      expected_state: entry.state, state, confirmed
    }).pipe(map(({ data }) => data));
  }
}
