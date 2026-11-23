import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { noAuthGuard } from './no-auth.guard';

describe('noAuthGuard', () => {
  const mockRoute = {} as ActivatedRouteSnapshot;
  const mockState = { url: '/login' } as RouterStateSnapshot;

  function setup(overrides: {
    authenticated?: boolean;
    hasUser?: boolean;
    hasTenant?: boolean;
    loadUserResult?: Observable<unknown>;
  }) {
    const authStub = {
      isAuthenticated: signal(overrides.authenticated ?? false),
      currentUser: signal(overrides.hasUser ? { id: 1, email: 'a@b.com' } : null),
      currentTenant: signal(overrides.hasTenant ? { id: 10, name: 'Acme' } : null),
      loadCurrentUser: vi.fn(() => overrides.loadUserResult ?? of(null)),
      clearLocalSession: vi.fn()
    };

    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: AuthService, useValue: authStub }]
    });

    return { router: TestBed.inject(Router), authStub };
  }

  it('allows unauthenticated users', () => {
    setup({ authenticated: false });
    const result = TestBed.runInInjectionContext(() => noAuthGuard(mockRoute, mockState));
    expect(result).toBe(true);
  });

  it('redirects authenticated users with tenant to /app/home', () => {
    const { router } = setup({ authenticated: true, hasUser: true, hasTenant: true });
    const result = TestBed.runInInjectionContext(() => noAuthGuard(mockRoute, mockState));
    expect(router.serializeUrl(result as UrlTree)).toBe('/app/home');
  });

  it('clears local session and allows access if loadCurrentUser fails', async () => {
    const { authStub } = setup({
      authenticated: true,
      hasUser: false,
      loadUserResult: throwError(() => new Error('invalid'))
    });

    const result$ = TestBed.runInInjectionContext(() =>
      noAuthGuard(mockRoute, mockState)
    ) as Observable<boolean | UrlTree>;
    const resolved = await firstValueFrom(result$);

    expect(resolved).toBe(true);
    expect(authStub.clearLocalSession).toHaveBeenCalledTimes(1);
  });
});
