import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';

export interface ChannelConnection {
  id: number;
  channel: string;
  provider: string;
  sender_address: string;
  display_name: string;
  status: string;
  verified: boolean;
  sandbox_only: boolean;
  credential_version: number;
}

export interface CampaignTemplateResult {
  template_id: number;
  template_version_id: number;
  name: string;
  channel: string;
  status: string;
}

export interface CampaignSummary {
  id: number;
  name: string;
  channel: string;
  purpose: string;
  status: string;
  version: number;
  recipient_counts: Record<string, number>;
}

export interface DispatchStubResult {
  claimed: number;
  accepted: number;
  suppressed: number;
  skipped_paused: number;
}

@Injectable({ providedIn: 'root' })
export class CampaignsApiService {
  private readonly http = inject(HttpClient);

  listConnections(): Observable<ChannelConnection[]> {
    return this.http
      .get<ApiResponse<ChannelConnection[]>>(`${OPERATIONAL_API_BASE_URL}/channels/connections`)
      .pipe(map((r) => r.data));
  }

  createConnection(payload: {
    channel: 'email';
    provider: 'stub' | 'resend';
    sender_address: string;
    display_name: string;
    verified: boolean;
    sandbox_only: boolean;
  }): Observable<ChannelConnection> {
    return this.http
      .post<ApiResponse<ChannelConnection>>(`${OPERATIONAL_API_BASE_URL}/channels/connections`, payload)
      .pipe(map((r) => r.data));
  }

  revokeConnection(connectionId: number): Observable<ChannelConnection> {
    return this.http
      .post<ApiResponse<ChannelConnection>>(`${OPERATIONAL_API_BASE_URL}/channels/connections/${connectionId}/revoke`, {})
      .pipe(map((r) => r.data));
  }

  createTemplate(payload: {
    name: string;
    channel: 'email';
    subject: string;
    body_text: string;
    approve_immediately: boolean;
  }): Observable<CampaignTemplateResult> {
    return this.http
      .post<ApiResponse<CampaignTemplateResult>>(`${OPERATIONAL_API_BASE_URL}/templates`, payload)
      .pipe(map((r) => r.data));
  }

  createCampaign(payload: {
    name: string;
    channel: 'email';
    purpose: string;
    template_version_id: number;
    connection_id: number;
    timezone_iana: string;
  }): Observable<CampaignSummary> {
    return this.http
      .post<ApiResponse<CampaignSummary>>(`${OPERATIONAL_API_BASE_URL}/campaigns`, payload)
      .pipe(map((r) => r.data));
  }

  approveCampaign(campaignId: number, expectedVersion: number): Observable<CampaignSummary> {
    return this.http
      .post<ApiResponse<CampaignSummary>>(`${OPERATIONAL_API_BASE_URL}/campaigns/${campaignId}/approve`, {
        expected_version: expectedVersion
      })
      .pipe(map((r) => r.data));
  }

  dispatchStub(limit = 20): Observable<DispatchStubResult> {
    return this.http
      .post<ApiResponse<DispatchStubResult>>(`${OPERATIONAL_API_BASE_URL}/campaigns/dispatch-stub?limit=${limit}`, {})
      .pipe(map((r) => r.data));
  }
}
