import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import { AnalyticsSummary } from '../domain/analytics.model';

@Injectable({ providedIn: 'root' })
export class AnalyticsApiService {
  private readonly http = inject(HttpClient);

  analyticsSummary(): Observable<AnalyticsSummary> {
    return this.http
      .get<ApiResponse<AnalyticsSummary>>(`${OPERATIONAL_API_BASE_URL}/analytics/summary`)
      .pipe(map((response) => response.data));
  }
}
