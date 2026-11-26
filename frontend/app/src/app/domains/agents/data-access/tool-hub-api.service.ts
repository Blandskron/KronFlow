import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import { toParams } from '@shared/utils/http.utils';
import {
  ChannelWebhookRouteItem,
  ExternalMappingItem,
  ToolDefinitionItem,
  ToolEffectMode,
  ToolInvocationItem,
  WebchatWidgetItem
} from '../domain/tool-hub.model';

@Injectable({ providedIn: 'root' })
export class ToolHubApiService {
  private readonly http = inject(HttpClient);

  listTools(): Observable<ToolDefinitionItem[]> {
    return this.http
      .get<ApiResponse<ToolDefinitionItem[]>>(`${OPERATIONAL_API_BASE_URL}/tools`)
      .pipe(map((res) => res.data));
  }

  createTool(payload: {
    tool_key: string;
    name: string;
    description?: string;
    effect_mode: ToolEffectMode;
    input_schema: Record<string, unknown>;
    connector_ref?: string;
    max_calls_per_hour?: number;
  }): Observable<ToolDefinitionItem> {
    return this.http
      .post<ApiResponse<ToolDefinitionItem>>(`${OPERATIONAL_API_BASE_URL}/tools`, payload)
      .pipe(map((res) => res.data));
  }

  updateTool(
    toolId: number,
    payload: {
      name?: string;
      description?: string;
      is_enabled?: boolean;
      max_calls_per_hour?: number;
    }
  ): Observable<ToolDefinitionItem> {
    return this.http
      .patch<ApiResponse<ToolDefinitionItem>>(`${OPERATIONAL_API_BASE_URL}/tools/${toolId}`, payload)
      .pipe(map((res) => res.data));
  }

  invokeTool(payload: {
    tool_key: string;
    arguments: Record<string, unknown>;
    idempotency_key: string;
    expected_schema_version?: number;
  }): Observable<ToolInvocationItem> {
    return this.http
      .post<ApiResponse<ToolInvocationItem>>(`${OPERATIONAL_API_BASE_URL}/tool-invocations`, payload)
      .pipe(map((res) => res.data));
  }

  listInvocations(filters?: { tool_key?: string; limit?: number }): Observable<ToolInvocationItem[]> {
    return this.http
      .get<ApiResponse<ToolInvocationItem[]>>(`${OPERATIONAL_API_BASE_URL}/tool-invocations`, {
        params: toParams({ ...filters })
      })
      .pipe(map((res) => res.data));
  }

  listWidgets(): Observable<WebchatWidgetItem[]> {
    return this.http
      .get<ApiResponse<WebchatWidgetItem[]>>(`${OPERATIONAL_API_BASE_URL}/webchat/widgets`)
      .pipe(map((res) => res.data));
  }

  createWidget(payload: {
    name: string;
    allowed_origins: string[];
    welcome_message?: string;
    session_ttl_minutes?: number;
    rate_limit_per_minute?: number;
    is_active?: boolean;
  }): Observable<WebchatWidgetItem> {
    return this.http
      .post<ApiResponse<WebchatWidgetItem>>(`${OPERATIONAL_API_BASE_URL}/webchat/widgets`, payload)
      .pipe(map((res) => res.data));
  }

  updateWidget(
    widgetId: number,
    payload: {
      name?: string;
      allowed_origins?: string[];
      welcome_message?: string;
      is_active?: boolean;
    }
  ): Observable<WebchatWidgetItem> {
    return this.http
      .patch<ApiResponse<WebchatWidgetItem>>(`${OPERATIONAL_API_BASE_URL}/webchat/widgets/${widgetId}`, payload)
      .pipe(map((res) => res.data));
  }

  listWebhookRoutes(): Observable<ChannelWebhookRouteItem[]> {
    return this.http
      .get<ApiResponse<ChannelWebhookRouteItem[]>>(`${OPERATIONAL_API_BASE_URL}/integrations/webhook-routes`)
      .pipe(map((res) => res.data));
  }

  createWebhookRoute(payload: {
    channel: 'whatsapp' | 'instagram' | 'messenger';
    external_account_id: string;
    verify_token: string;
    app_secret: string;
  }): Observable<ChannelWebhookRouteItem> {
    return this.http
      .post<ApiResponse<ChannelWebhookRouteItem>>(`${OPERATIONAL_API_BASE_URL}/integrations/webhook-routes`, payload)
      .pipe(map((res) => res.data));
  }

  deactivateWebhookRoute(routeId: number): Observable<ChannelWebhookRouteItem> {
    return this.http
      .post<ApiResponse<ChannelWebhookRouteItem>>(
        `${OPERATIONAL_API_BASE_URL}/integrations/webhook-routes/${routeId}/deactivate`,
        {}
      )
      .pipe(map((res) => res.data));
  }

  listMappings(syncState?: string): Observable<ExternalMappingItem[]> {
    return this.http
      .get<ApiResponse<ExternalMappingItem[]>>(`${OPERATIONAL_API_BASE_URL}/integrations/mappings`, {
        params: toParams({ sync_state: syncState })
      })
      .pipe(map((res) => res.data));
  }

  resolveMapping(mappingId: number, resolution: 'synced' | 'disconnected'): Observable<ExternalMappingItem> {
    return this.http
      .post<ApiResponse<ExternalMappingItem>>(`${OPERATIONAL_API_BASE_URL}/integrations/mappings/${mappingId}/resolve`, {
        resolution
      })
      .pipe(map((res) => res.data));
  }

  callMcp(method: string, params: Record<string, unknown> = {}): Observable<Record<string, unknown>> {
    return this.http.post<Record<string, unknown>>(`${OPERATIONAL_API_BASE_URL}/mcp`, {
      jsonrpc: '2.0',
      id: 'ui-inspect-1',
      method,
      params
    });
  }
}
