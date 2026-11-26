import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import {
  AgentConfigurePayload,
  AgentProfile,
  AgentRevision,
  AgentUpdatePayload
} from '../domain/agent-profile.model';

@Injectable({ providedIn: 'root' })
export class AgentsApiService {
  private readonly http = inject(HttpClient);

  listAgents(): Observable<AgentProfile[]> {
    return this.http
      .get<ApiResponse<AgentProfile[]>>(`${OPERATIONAL_API_BASE_URL}/agents`)
      .pipe(map((response) => response.data));
  }

  getAgent(agentId: number): Observable<AgentProfile> {
    return this.http
      .get<ApiResponse<AgentProfile>>(`${OPERATIONAL_API_BASE_URL}/agents/${agentId}`)
      .pipe(map((response) => response.data));
  }

  configureAgent(payload: AgentConfigurePayload): Observable<AgentProfile> {
    return this.http
      .post<ApiResponse<AgentProfile>>(`${OPERATIONAL_API_BASE_URL}/agents/configure`, payload)
      .pipe(map((response) => response.data));
  }

  updateAgent(agentId: number, payload: AgentUpdatePayload): Observable<AgentProfile> {
    return this.http
      .patch<ApiResponse<AgentProfile>>(`${OPERATIONAL_API_BASE_URL}/agents/${agentId}`, payload)
      .pipe(map((response) => response.data));
  }

  publishAgent(agentId: number, expectedVersion: number, note?: string): Observable<AgentRevision> {
    return this.http
      .post<ApiResponse<AgentRevision>>(`${OPERATIONAL_API_BASE_URL}/agents/${agentId}/publish`, {
        expected_version: expectedVersion,
        note: note || null
      })
      .pipe(map((response) => response.data));
  }

  listRevisions(agentId: number): Observable<AgentRevision[]> {
    return this.http
      .get<ApiResponse<AgentRevision[]>>(`${OPERATIONAL_API_BASE_URL}/agents/${agentId}/revisions`)
      .pipe(map((response) => response.data));
  }

  rollbackAgent(agentId: number, expectedVersion: number, revisionId: number): Observable<AgentProfile> {
    return this.http
      .post<ApiResponse<AgentProfile>>(`${OPERATIONAL_API_BASE_URL}/agents/${agentId}/rollback`, {
        expected_version: expectedVersion,
        revision_id: revisionId
      })
      .pipe(map((response) => response.data));
  }
}
