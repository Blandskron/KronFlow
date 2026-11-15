import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import { AgentProfile } from '../domain/agent-profile.model';

@Injectable({ providedIn: 'root' })
export class AgentsApiService {
  private readonly http = inject(HttpClient);

  listAgents(): Observable<AgentProfile[]> {
    return this.http.get<ApiResponse<AgentProfile[]>>(`${OPERATIONAL_API_BASE_URL}/agents`).pipe(map((response) => response.data));
  }

  configureAgent(payload: { name: string; role: string; prompt_config?: Record<string, unknown> }): Observable<AgentProfile> {
    return this.http
      .post<ApiResponse<AgentProfile>>(`${OPERATIONAL_API_BASE_URL}/agents/configure`, payload)
      .pipe(map((response) => response.data));
  }
}
