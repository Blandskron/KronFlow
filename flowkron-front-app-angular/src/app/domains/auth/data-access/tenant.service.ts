import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';
import { API_BASE_URL } from '@core/config/api.config';
import { ApiResponse } from '@shared/types/api.types';
import {
  InviteMemberResponse,
  OperationalRuntimeInfo,
  Tenant,
  TenantInvitation,
  TenantMembership,
  TenantUpdateRequest
} from '../domain/auth.model';

@Injectable({ providedIn: 'root' })
export class TenantService {
  private readonly http = inject(HttpClient);

  listMembers(tenantId: number): Observable<TenantMembership[]> {
    return this.http
      .get<ApiResponse<TenantMembership[]>>(`${API_BASE_URL}/tenants/${tenantId}/members/`)
      .pipe(map((response) => response.data));
  }

  updateTenant(tenantId: number, request: TenantUpdateRequest): Observable<Tenant> {
    return this.http
      .patch<ApiResponse<Tenant> | Tenant>(`${API_BASE_URL}/tenants/${tenantId}/`, request)
      .pipe(map((response) => this.unwrap(response)));
  }

  uploadTenantLogo(tenantId: number, file: File): Observable<Tenant> {
    const formData = new FormData();
    formData.append('image', file);
    return this.http
      .post<ApiResponse<Tenant>>(`${API_BASE_URL}/tenants/${tenantId}/logo/`, formData)
      .pipe(map((response) => response.data));
  }

  inviteMember(
    tenantId: number,
    request: { email: string; role_code: string; expires_in_days?: number }
  ): Observable<InviteMemberResponse> {
    return this.http
      .post<ApiResponse<InviteMemberResponse>>(`${API_BASE_URL}/tenants/${tenantId}/invite/`, request)
      .pipe(map((response) => response.data));
  }

  listInvitations(tenantId: number): Observable<TenantInvitation[]> {
    return this.http
      .get<ApiResponse<TenantInvitation[]>>(`${API_BASE_URL}/tenants/${tenantId}/invitations/`)
      .pipe(map((response) => response.data));
  }

  updateMember(
    tenantId: number,
    membershipId: number,
    request: { role_codes?: string[]; status?: string }
  ): Observable<TenantMembership> {
    return this.http
      .patch<ApiResponse<TenantMembership>>(`${API_BASE_URL}/tenants/${tenantId}/members/${membershipId}/`, request)
      .pipe(map((response) => response.data));
  }

  removeMember(tenantId: number, membershipId: number): Observable<TenantMembership> {
    return this.http
      .delete<ApiResponse<TenantMembership>>(`${API_BASE_URL}/tenants/${tenantId}/members/${membershipId}/`)
      .pipe(map((response) => response.data));
  }

  previewInvitation(token: string): Observable<TenantInvitation> {
    return this.http
      .get<ApiResponse<TenantInvitation>>(`${API_BASE_URL}/tenants/invitations/preview/`, { params: { token } })
      .pipe(map((response) => response.data));
  }

  acceptInvitation(request: { token: string; display_name?: string }): Observable<TenantMembership> {
    return this.http
      .post<ApiResponse<TenantMembership>>(`${API_BASE_URL}/tenants/invitations/accept/`, request)
      .pipe(map((response) => response.data));
  }

  rejectInvitation(token: string): Observable<TenantInvitation> {
    return this.http
      .post<ApiResponse<TenantInvitation>>(`${API_BASE_URL}/tenants/invitations/reject/`, { token })
      .pipe(map((response) => response.data));
  }

  getRuntime(tenantId: number): Observable<OperationalRuntimeInfo | null> {
    return this.http
      .get<ApiResponse<OperationalRuntimeInfo | null>>(`${API_BASE_URL}/tenants/${tenantId}/runtime/`)
      .pipe(map((response) => response.data));
  }

  provisionRuntime(tenantId: number): Observable<{ runtime: OperationalRuntimeInfo | null; ingest_key?: string; show_ingest_key_once: boolean }> {
    return this.http
      .post<ApiResponse<{ runtime: OperationalRuntimeInfo | null; ingest_key?: string; show_ingest_key_once: boolean }>>(
        `${API_BASE_URL}/tenants/${tenantId}/runtime/provision/`,
        {}
      )
      .pipe(map((response) => response.data));
  }

  activateSubscription(tenantId: number, plan = 'starter'): Observable<Tenant> {
    return this.http
      .post<ApiResponse<Tenant>>(`${API_BASE_URL}/tenants/${tenantId}/subscription/activate/`, { plan })
      .pipe(map((response) => response.data));
  }

  private unwrap<T>(response: ApiResponse<T> | T): T {
    if (this.isApiResponse(response)) {
      return response.data;
    }
    return response;
  }

  private isApiResponse<T>(response: ApiResponse<T> | T): response is ApiResponse<T> {
    return Boolean(response && typeof response === 'object' && 'data' in response && 'success' in response);
  }
}
