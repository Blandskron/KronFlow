import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse, PaginatedResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';

export interface AIProposalItem {
  id: number;
  action_type: string;
  resource_type: 'contact' | 'lead' | 'opportunity' | 'conversation';
  resource_id: number;
  arguments: Record<string, unknown>;
  status: 'pending' | 'approved' | 'rejected' | 'executed' | 'expired';
  proposal_version: number;
  proposed_by: string;
  rationale: string | null;
  expires_at: string;
  reviewed_by: string | null;
  executed_by: string | null;
  created_at: string;
}

@Injectable({ providedIn: 'root' })
export class AIProposalsApiService {
  private readonly http = inject(HttpClient);

  list(status?: string, limit = 50, offset = 0): Observable<PaginatedResponse<AIProposalItem>> {
    return this.http
      .get<ApiResponse<PaginatedResponse<AIProposalItem>>>(`${OPERATIONAL_API_BASE_URL}/ai-proposals`, {
        params: toParams({ status, limit, offset })
      })
      .pipe(map((r) => r.data));
  }

  approve(proposalId: number, expectedVersion: number, reviewNote?: string): Observable<AIProposalItem> {
    return this.http
      .post<ApiResponse<AIProposalItem>>(`${OPERATIONAL_API_BASE_URL}/ai-proposals/${proposalId}/approve`, {
        expected_version: expectedVersion,
        review_note: reviewNote
      })
      .pipe(map((r) => r.data));
  }

  reject(proposalId: number, expectedVersion: number, reviewNote?: string): Observable<AIProposalItem> {
    return this.http
      .post<ApiResponse<AIProposalItem>>(`${OPERATIONAL_API_BASE_URL}/ai-proposals/${proposalId}/reject`, {
        expected_version: expectedVersion,
        review_note: reviewNote
      })
      .pipe(map((r) => r.data));
  }

  execute(proposalId: number, expectedVersion: number): Observable<AIProposalItem> {
    return this.http
      .post<ApiResponse<AIProposalItem>>(`${OPERATIONAL_API_BASE_URL}/ai-proposals/${proposalId}/execute`, {
        expected_version: expectedVersion
      })
      .pipe(map((r) => r.data));
  }
}
