import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, finalize, map, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { API_BASE_URL } from '@core/config/api.config';
import { ApiErrorBody, ApiResponse } from '@shared/types/api.types';
import {
  AuthError,
  LoginRequest,
  LoginResponse,
  MeResponse,
  ProfileUpdateRequest,
  RefreshResponse,
  SubscriptionInfo,
  Tenant,
  TenantOnboardingRequest,
  TenantOnboardingResponse,
  User
} from '../domain/auth.model';
import {
  clearTokens,
  readAccessToken,
  readRefreshToken,
  readTenantId,
  writeTenantId,
  writeTokens
} from '@core/utils/token-storage';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private refreshRequest$: Observable<RefreshResponse> | null = null;

  readonly accessToken = signal<string | null>(readAccessToken());
  readonly refreshToken = signal<string | null>(readRefreshToken());
  readonly currentTenantId = signal<number | null>(readTenantId());
  readonly currentUser = signal<User | null>(null);
  readonly currentTenant = signal<Tenant | null>(null);
  readonly roles = signal<string[]>([]);
  readonly permissions = signal<string[]>([]);
  readonly subscription = signal<SubscriptionInfo | null>(null);
  readonly isLoading = signal(false);

  readonly isAuthenticated = computed(() => Boolean(this.accessToken()));
  readonly requiresTenantOnboarding = computed(() => this.isAuthenticated() && Boolean(this.currentUser()) && !this.currentTenant());
  readonly displayName = computed(() => {
    const user = this.currentUser();
    return user?.profile.display_name || user?.email.split('@')[0] || 'Usuario';
  });

  getAccessToken(): string | null {
    return this.accessToken();
  }

  getTenantId(): number | null {
    return this.currentTenantId();
  }

  setCurrentTenant(tenant: Tenant | null): void {
    this.currentTenant.set(tenant);
    this.currentTenantId.set(tenant?.id ?? null);
    writeTenantId(tenant?.id ?? null);
  }

  login(request: LoginRequest): Observable<MeResponse> {
    this.isLoading.set(true);
    return this.http.post<ApiResponse<LoginResponse>>(`${API_BASE_URL}/auth/login/`, request).pipe(
      tap((response) => this.applyLoginResponse(response.data)),
      switchMap(() => this.fetchCurrentUser()),
      finalize(() => this.isLoading.set(false)),
      catchError((error) => throwError(() => this.toAuthError(error)))
    );
  }

  loadCurrentUser(): Observable<MeResponse | null> {
    if (!this.accessToken()) {
      return of(null);
    }
    return this.http.get<ApiResponse<MeResponse>>(`${API_BASE_URL}/auth/me/`).pipe(
      map((response) => response.data),
      tap((me) => this.applyMeResponse(me)),
      catchError((error) => {
        this.clearLocalSession();
        return throwError(() => this.toAuthError(error));
      })
    );
  }

  refreshSession(): Observable<RefreshResponse> {
    const refresh = this.refreshToken();
    if (!refresh) {
      return throwError(() => ({ code: 'TOKEN_NOT_VALID', message: 'Sesion expirada.' } satisfies AuthError));
    }

    if (!this.refreshRequest$) {
      this.refreshRequest$ = this.http
        .post<ApiResponse<RefreshResponse>>(`${API_BASE_URL}/auth/refresh/`, { refresh })
        .pipe(
          map((response) => response.data),
          tap((tokens) => this.storeTokens(tokens, this.currentTenantId())),
          finalize(() => {
            this.refreshRequest$ = null;
          }),
          shareReplay({ bufferSize: 1, refCount: false })
        );
    }

    return this.refreshRequest$;
  }

  logout(): Observable<void> {
    if (!this.accessToken()) {
      this.clearLocalSession();
      return of(void 0);
    }

    return this.http.post<ApiResponse<{ revoked: boolean }>>(`${API_BASE_URL}/auth/logout/`, {}).pipe(
      map(() => void 0),
      catchError(() => of(void 0)),
      tap(() => this.clearLocalSession())
    );
  }

  confirmEmail(token: string): Observable<void> {
    return this.http.post<ApiResponse<{ verified: boolean }>>(`${API_BASE_URL}/auth/email/confirm/`, { token }).pipe(
      map(() => void 0),
      catchError((error) => throwError(() => this.toAuthError(error)))
    );
  }

  requestPasswordReset(email: string): Observable<void> {
    return this.http.post<ApiResponse<{ sent: boolean }>>(`${API_BASE_URL}/auth/password/forgot/`, { email }).pipe(
      map(() => void 0),
      catchError((error) => throwError(() => this.toAuthError(error)))
    );
  }

  resetPassword(token: string, newPassword: string): Observable<void> {
    return this.http
      .post<ApiResponse<{ reset: boolean }>>(`${API_BASE_URL}/auth/password/reset/`, {
        token,
        new_password: newPassword
      })
      .pipe(
        map(() => void 0),
        catchError((error) => throwError(() => this.toAuthError(error)))
      );
  }

  updateProfile(request: ProfileUpdateRequest): Observable<User> {
    return this.http.patch<ApiResponse<User>>(`${API_BASE_URL}/auth/profile/`, request).pipe(
      map((response) => response.data),
      tap((user) => this.currentUser.set(user)),
      catchError((error) => throwError(() => this.toAuthError(error)))
    );
  }

  uploadAvatar(file: File): Observable<User> {
    const formData = new FormData();
    formData.append('image', file);
    return this.http.post<ApiResponse<User>>(`${API_BASE_URL}/auth/profile/avatar/`, formData).pipe(
      map((response) => response.data),
      tap((user) => this.currentUser.set(user)),
      catchError((error) => throwError(() => this.toAuthError(error)))
    );
  }

  clearLocalSession(): void {
    clearTokens();
    this.accessToken.set(null);
    this.refreshToken.set(null);
    this.currentTenantId.set(null);
    this.currentUser.set(null);
    this.currentTenant.set(null);
    this.roles.set([]);
    this.permissions.set([]);
    this.subscription.set(null);
  }

  completeTenantOnboarding(request: TenantOnboardingRequest): Observable<MeResponse> {
    this.isLoading.set(true);
    return this.http.post<ApiResponse<TenantOnboardingResponse>>(`${API_BASE_URL}/tenants/onboarding/`, request).pipe(
      tap((response) => this.applyOnboardingResponse(response.data)),
      switchMap(() => this.fetchCurrentUser()),
      finalize(() => this.isLoading.set(false)),
      catchError((error) => throwError(() => this.toAuthError(error)))
    );
  }

  hasRole(role: string): boolean {
    return this.roles().includes(role);
  }

  hasPermission(permission: string): boolean {
    return this.permissions().includes(permission);
  }

  private applyLoginResponse(data: LoginResponse): void {
    this.storeTokens({ access: data.access, refresh: data.refresh }, data.tenant_id);
    this.roles.set(data.roles);
    this.permissions.set(data.permissions);
    this.subscription.set(data.subscription);
  }

  private applyOnboardingResponse(data: TenantOnboardingResponse): void {
    this.storeTokens({ access: data.access, refresh: data.refresh }, data.tenant_id);
    this.currentTenant.set(data.tenant);
    this.currentTenantId.set(data.tenant_id);
    writeTenantId(data.tenant_id);
    this.roles.set(data.roles);
    this.permissions.set(data.permissions);
    this.subscription.set(data.tenant.subscription ?? null);
  }

  private fetchCurrentUser(): Observable<MeResponse> {
    return this.http.get<ApiResponse<MeResponse>>(`${API_BASE_URL}/auth/me/`).pipe(
      map((response) => response.data),
      tap((me) => this.applyMeResponse(me))
    );
  }

  private applyMeResponse(me: MeResponse): void {
    this.currentUser.set(me.user);
    this.currentTenant.set(me.tenant);
    this.currentTenantId.set(me.tenant?.id ?? null);
    writeTenantId(this.currentTenantId());
    this.roles.set(me.roles);
    this.permissions.set(me.permissions);
    this.subscription.set(me.subscription);
  }

  private storeTokens(tokens: RefreshResponse, tenantId?: number | null): void {
    writeTokens(tokens, tenantId);
    this.accessToken.set(tokens.access);
    this.refreshToken.set(tokens.refresh);
    if (tenantId) {
      this.currentTenantId.set(tenantId);
    }
  }

  private toAuthError(error: unknown): AuthError {
    if (error instanceof HttpErrorResponse) {
      const body = error.error as Partial<ApiErrorBody> | undefined;
      return {
        code: body?.error_code || body?.code || 'REQUEST_FAILED',
        message: body?.detail || body?.message || body?.title || 'No pudimos completar la solicitud.',
        details: body?.errors || body?.details || body
      };
    }

    return {
      code: 'REQUEST_FAILED',
      message: 'No pudimos completar la solicitud.',
      details: error
    };
  }
}
