import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { Lead } from '../domain/lead.model';
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
  } = {}): Observable<PaginatedResponse<Lead>> {
    return this.http
      .get<ApiResponse<PaginatedResponse<Lead>>>(`${OPERATIONAL_API_BASE_URL}/leads`, {
        params: toParams(filters)
      })
      .pipe(map((response) => response.data));
  }
}
