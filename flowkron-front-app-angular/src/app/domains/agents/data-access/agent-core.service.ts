import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { AGENT_CORE_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import {
  AgentMessageRequest,
  AgentMessageResponse,
  BusinessContextStatus,
  ContextDocumentPayload,
  DocumentRead,
  TemplateRead,
  SetupSessionRead,
  GeneratedContextRead,
  RuleRead,
  RuleCreate,
  RulePatch,
  RetrievalTrace
} from '../domain/agent-core.model';

@Injectable({ providedIn: 'root' })
export class AgentCoreService {
  private readonly http = inject(HttpClient);

  // 1. Documentos
  listDocuments(): Observable<DocumentRead[]> {
    return this.http
      .get<ApiResponse<DocumentRead[]>>(`${AGENT_CORE_API_BASE_URL}/context/documents`)
      .pipe(map((response) => response.data));
  }

  getBusinessContextStatus(): Observable<BusinessContextStatus> {
    return this.http
      .get<ApiResponse<BusinessContextStatus>>(`${AGENT_CORE_API_BASE_URL}/context/status`)
      .pipe(map((response) => response.data));
  }

  getDocument(id: number): Observable<DocumentRead> {
    return this.http
      .get<ApiResponse<DocumentRead>>(`${AGENT_CORE_API_BASE_URL}/context/documents/${id}`)
      .pipe(map((response) => response.data));
  }

  uploadDocument(payload: ContextDocumentPayload): Observable<DocumentRead> {
    return this.http
      .post<ApiResponse<DocumentRead>>(`${AGENT_CORE_API_BASE_URL}/context/documents/upload`, payload)
      .pipe(map((response) => response.data));
  }

  uploadDocumentFile(file: File, title: string, status = 'active', priority = 100): Observable<DocumentRead> {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('status', status);
    formData.append('priority', String(priority));
    formData.append('file', file);
    return this.http
      .post<ApiResponse<DocumentRead>>(`${AGENT_CORE_API_BASE_URL}/context/documents/upload-file`, formData)
      .pipe(map((response) => response.data));
  }

  uploadDocumentFileEvents(file: File, title: string, status = 'active', priority = 100): Observable<HttpEvent<ApiResponse<DocumentRead>>> {
    const formData = new FormData();
    formData.append('title', title);
    formData.append('status', status);
    formData.append('priority', String(priority));
    formData.append('file', file);
    return this.http.post<ApiResponse<DocumentRead>>(`${AGENT_CORE_API_BASE_URL}/context/documents/upload-file`, formData, {
      observe: 'events',
      reportProgress: true
    });
  }

  patchDocument(id: number, payload: Partial<ContextDocumentPayload>): Observable<DocumentRead> {
    return this.http
      .patch<ApiResponse<DocumentRead>>(`${AGENT_CORE_API_BASE_URL}/context/documents/${id}`, payload)
      .pipe(map((response) => response.data));
  }

  deleteDocument(id: number): Observable<void> {
    return this.http
      .delete<ApiResponse<void>>(`${AGENT_CORE_API_BASE_URL}/context/documents/${id}`)
      .pipe(map(() => undefined));
  }

  // 2. Plantillas
  listTemplates(): Observable<TemplateRead[]> {
    return this.http
      .get<ApiResponse<any[]>>(`${AGENT_CORE_API_BASE_URL}/context/templates`)
      .pipe(map((response) => this.normalizeTemplates(response.data)));
  }

  downloadTemplate(id: number): Observable<{ blob: Blob; filename: string }> {
    return this.http
      .get(`${AGENT_CORE_API_BASE_URL}/context/templates/${id}/download`, {
        observe: 'response',
        responseType: 'blob'
      })
      .pipe(
        map((response) => ({
          blob: response.body ?? new Blob(),
          filename: this.filenameFromDisposition(response.headers.get('content-disposition')) ?? `template-${id}`
        }))
      );
  }

  // 4. Asistente IA (Setup Onboarding)
  createSetupSession(companyName: string, industry: string): Observable<SetupSessionRead> {
    return this.http
      .post<ApiResponse<SetupSessionRead>>(`${AGENT_CORE_API_BASE_URL}/setup-chat/sessions`, {
        objective: `build_business_context:${companyName}:${industry}`
      })
      .pipe(map((response) => response.data));
  }

  sendSetupMessage(sessionId: string, message: string): Observable<SetupSessionRead> {
    return this.http
      .post<ApiResponse<SetupSessionRead>>(`${AGENT_CORE_API_BASE_URL}/setup-chat/sessions/${sessionId}/messages`, {
        content: message
      })
      .pipe(map((response) => response.data));
  }

  generateContext(sessionId: string): Observable<GeneratedContextRead> {
    return this.http
      .post<ApiResponse<GeneratedContextRead>>(`${AGENT_CORE_API_BASE_URL}/setup-chat/sessions/${sessionId}/generate-context`, {})
      .pipe(map((response) => response.data));
  }

  // 5. Reglas y Correcciones
  listRules(): Observable<RuleRead[]> {
    return this.http
      .get<ApiResponse<RuleRead[]>>(`${AGENT_CORE_API_BASE_URL}/agent/rules`)
      .pipe(map((response) => response.data));
  }

  createRule(payload: RuleCreate): Observable<RuleRead> {
    return this.http
      .post<ApiResponse<RuleRead>>(`${AGENT_CORE_API_BASE_URL}/agent/rules`, payload)
      .pipe(map((response) => response.data));
  }

  patchRule(id: number, payload: RulePatch): Observable<RuleRead> {
    return this.http
      .patch<ApiResponse<RuleRead>>(`${AGENT_CORE_API_BASE_URL}/agent/rules/${id}`, payload)
      .pipe(map((response) => response.data));
  }

  deleteRule(id: number): Observable<void> {
    return this.http
      .delete<ApiResponse<void>>(`${AGENT_CORE_API_BASE_URL}/agent/rules/${id}`)
      .pipe(map(() => undefined));
  }

  // 6. Trazabilidad y Simulación
  simulate(payload: AgentMessageRequest): Observable<AgentMessageResponse> {
    return this.http
      .post<ApiResponse<AgentMessageResponse>>(`${AGENT_CORE_API_BASE_URL}/agent/simulate`, payload)
      .pipe(map((response) => response.data));
  }

  getConversationTraces(conversationId: string): Observable<RetrievalTrace[]> {
    return this.http
      .get<ApiResponse<RetrievalTrace[]>>(`${AGENT_CORE_API_BASE_URL}/agent/conversations/${conversationId}/traces`)
      .pipe(map((response) => response.data));
  }

  getTraceDetails(traceId: number): Observable<any> {
    return this.http
      .get<ApiResponse<any>>(`${AGENT_CORE_API_BASE_URL}/agent/traces/${traceId}`)
      .pipe(map((response) => response.data));
  }

  private filenameFromDisposition(disposition: string | null): string | null {
    if (!disposition) {
      return null;
    }
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (encoded?.[1]) {
      return decodeURIComponent(encoded[1]);
    }
    const plain = disposition.match(/filename="?([^";]+)"?/i);
    return plain?.[1] ?? null;
  }

  private normalizeTemplates(rawTemplates: any[]): TemplateRead[] {
    if (!Array.isArray(rawTemplates)) {
      return [];
    }

    if (rawTemplates.every((template) => Array.isArray(template.download_options))) {
      return rawTemplates as TemplateRead[];
    }

    const grouped = new Map<string, TemplateRead>();
    rawTemplates.forEach((template) => {
      if (!template?.code || !template?.format || !template?.id) {
        return;
      }

      const current: TemplateRead = grouped.get(template.code) ?? {
        id: grouped.size + 1,
        code: template.code,
        name: template.name,
        description: template.description,
        fields: template.fields ?? [],
        download_options: []
      };

      current.download_options.push({
        format: template.format as 'docx' | 'pdf',
        template_id: template.id,
        filename: `${template.code}.${template.format}`,
        media_type:
          template.format === 'docx'
            ? 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            : 'application/pdf'
      });
      grouped.set(template.code, current);
    });

    return Array.from(grouped.values());
  }
}
