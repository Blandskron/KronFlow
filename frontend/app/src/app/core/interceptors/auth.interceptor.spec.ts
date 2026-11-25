import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { API_BASE_URL, OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { authInterceptor } from './auth.interceptor';

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let authStub: {
    getAccessToken: ReturnType<typeof vi.fn>;
    getTenantId: ReturnType<typeof vi.fn>;
    refreshSession: ReturnType<typeof vi.fn>;
    clearLocalSession: ReturnType<typeof vi.fn>;
  };
  let routerStub: { navigate: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    authStub = {
      getAccessToken: vi.fn(() => 'token-123'),
      getTenantId: vi.fn(() => 7),
      refreshSession: vi.fn(() => of({ access: 'token-refreshed', refresh: 'ref-2' })),
      clearLocalSession: vi.fn()
    };
    routerStub = {
      navigate: vi.fn(() => Promise.resolve(true))
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([authInterceptor])),
        provideHttpClientTesting(),
        { provide: AuthService, useValue: authStub },
        { provide: Router, useValue: routerStub }
      ]
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('attaches X-Correlation-ID, Authorization, and X-Tenant-ID to API requests', () => {
    http.get(`${API_BASE_URL}/auth/me/`).subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/me/`);
    expect(req.request.headers.get('X-Correlation-ID')).toBeTruthy();
    expect(req.request.headers.get('Authorization')).toBe('Bearer token-123');
    expect(req.request.headers.get('X-Tenant-ID')).toBe('7');
    req.flush({ data: {} });
  });

  it('does not attach Authorization or X-Tenant-ID to login requests', () => {
    http.post(`${API_BASE_URL}/auth/login/`, {}).subscribe();

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/login/`);
    expect(req.request.headers.get('X-Correlation-ID')).toBeTruthy();
    expect(req.request.headers.has('Authorization')).toBe(false);
    expect(req.request.headers.has('X-Tenant-ID')).toBe(false);
    req.flush({ data: {} });
  });

  it('refreshes session and retries on 401', () => {
    let result: unknown;
    http.get(`${OPERATIONAL_API_BASE_URL}/contacts`).subscribe((res) => (result = res));

    const first = httpMock.expectOne(`${OPERATIONAL_API_BASE_URL}/contacts`);
    first.flush({ detail: 'Unauthorized' }, { status: 401, statusText: 'Unauthorized' });

    expect(authStub.refreshSession).toHaveBeenCalledTimes(1);

    const retry = httpMock.expectOne(`${OPERATIONAL_API_BASE_URL}/contacts`);
    expect(retry.request.headers.get('Authorization')).toBe('Bearer token-refreshed');
    retry.flush({ items: [] });

    expect(result).toEqual({ items: [] });
  });

  it('clears local session and redirects to /login when refresh fails', () => {
    authStub.refreshSession.mockReturnValueOnce(throwError(() => new Error('refresh failed')));

    let errored = false;
    http.get(`${API_BASE_URL}/auth/me/`).subscribe({
      error: () => (errored = true)
    });

    const req = httpMock.expectOne(`${API_BASE_URL}/auth/me/`);
    req.flush({}, { status: 401, statusText: 'Unauthorized' });

    expect(errored).toBe(true);
    expect(authStub.clearLocalSession).toHaveBeenCalledTimes(1);
    expect(routerStub.navigate).toHaveBeenCalledWith(['/login']);
  });
});
