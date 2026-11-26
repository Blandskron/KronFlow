import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';
import {
  WorkflowDefinitionItem,
  WorkflowGraph,
  WorkflowRevisionItem,
  WorkflowRunItem,
  WorkflowSimulationResult,
  WorkflowTemplateItem,
  WorkflowValidationResult
} from '../domain/workflow-engine.model';

@Injectable({ providedIn: 'root' })
export class WorkflowsApiService {
  private readonly http = inject(HttpClient);

  listTemplates(): Observable<WorkflowTemplateItem[]> {
    return this.http
      .get<ApiResponse<WorkflowTemplateItem[]>>(`${OPERATIONAL_API_BASE_URL}/workflows/templates`)
      .pipe(map((response) => response.data));
  }

  listWorkflows(): Observable<WorkflowDefinitionItem[]> {
    return this.http
      .get<ApiResponse<WorkflowDefinitionItem[]>>(`${OPERATIONAL_API_BASE_URL}/workflows`)
      .pipe(map((response) => response.data));
  }

  createWorkflow(payload: {
    name: string;
    description?: string;
    trigger_event_type: string;
    graph: WorkflowGraph;
  }): Observable<WorkflowDefinitionItem> {
    return this.http
      .post<ApiResponse<WorkflowDefinitionItem>>(`${OPERATIONAL_API_BASE_URL}/workflows`, payload)
      .pipe(map((response) => response.data));
  }

  updateDraft(
    workflowId: number,
    payload: {
      name?: string;
      description?: string;
      status?: 'draft' | 'active' | 'paused' | 'archived';
      trigger_event_type?: string;
      graph?: WorkflowGraph;
      expected_version: number;
    }
  ): Observable<WorkflowDefinitionItem> {
    return this.http
      .patch<ApiResponse<WorkflowDefinitionItem>>(`${OPERATIONAL_API_BASE_URL}/workflows/${workflowId}/draft`, payload)
      .pipe(map((response) => response.data));
  }

  validateWorkflow(workflowId: number): Observable<WorkflowValidationResult> {
    return this.http
      .post<ApiResponse<WorkflowValidationResult>>(`${OPERATIONAL_API_BASE_URL}/workflows/${workflowId}/validate`, {})
      .pipe(map((response) => response.data));
  }

  simulateWorkflow(workflowId: number, samplePayload: Record<string, unknown>): Observable<WorkflowSimulationResult> {
    return this.http
      .post<ApiResponse<WorkflowSimulationResult>>(`${OPERATIONAL_API_BASE_URL}/workflows/${workflowId}/simulate`, {
        sample_payload: samplePayload
      })
      .pipe(map((response) => response.data));
  }

  publishWorkflow(workflowId: number, expectedVersion: number, note?: string): Observable<WorkflowRevisionItem> {
    return this.http
      .post<ApiResponse<WorkflowRevisionItem>>(`${OPERATIONAL_API_BASE_URL}/workflows/${workflowId}/publish`, {
        expected_version: expectedVersion,
        note: note || null
      })
      .pipe(map((response) => response.data));
  }

  listRevisions(workflowId: number): Observable<WorkflowRevisionItem[]> {
    return this.http
      .get<ApiResponse<WorkflowRevisionItem[]>>(`${OPERATIONAL_API_BASE_URL}/workflows/${workflowId}/revisions`)
      .pipe(map((response) => response.data));
  }

  processTick(): Observable<Record<string, number>> {
    return this.http
      .post<ApiResponse<Record<string, number>>>(`${OPERATIONAL_API_BASE_URL}/workflows/process-tick`, {})
      .pipe(map((response) => response.data));
  }

  listRuns(filters?: { workflow_id?: number; status?: string; limit?: number }): Observable<WorkflowRunItem[]> {
    return this.http
      .get<ApiResponse<WorkflowRunItem[]>>(`${OPERATIONAL_API_BASE_URL}/workflow-runs`, {
        params: toParams({ ...filters })
      })
      .pipe(map((response) => response.data));
  }

  cancelRun(runId: number): Observable<WorkflowRunItem> {
    return this.http
      .post<ApiResponse<WorkflowRunItem>>(`${OPERATIONAL_API_BASE_URL}/workflow-runs/${runId}/cancel`, {})
      .pipe(map((response) => response.data));
  }
}
