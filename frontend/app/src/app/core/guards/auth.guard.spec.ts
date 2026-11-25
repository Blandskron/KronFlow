import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree, provideRouter } from '@angular/router';
import { Observable, firstValueFrom, of, throwError } from 'rxjs';
import { vi } from 'vitest';
import { AuthService } from '@domains/auth/data-access/auth-api.service';
import { authGuard } from './auth.guard';

describe('authGuard', () => {
  const mockRoute = {} as ActivatedRouteSnapshot;
  const makeState = (url: string) => ({ url }) as RouterStateSnapshot;

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
      loadCurrentUser: vi.fn(() => overrides.loadUserResult ?? of(null))
    };

    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: AuthService, useValue: authStub }]
    });

    return { router: TestBed.inject(Router), authStub };
  }

  it('redirects unauthenticated users to /login', () => {
    const { router } = setup({ authenticated: false });
    const result = TestBed.runInInjectionContext(() => authGuard(mockRoute, makeState('/app/home')));

    expect(result instanceof UrlTree).toBe(true);
    expect(router.serializeUrl(result as UrlTree)).toBe('/login');
  });

  it('redirects authenticated users without tenant to /onboarding/company', () => {
    const { router } = setup({ authenticated: true, hasUser: true, hasTenant: false });
    const result = TestBed.runInInjectionContext(() => authGuard(mockRoute, makeState('/app/home')));

    expect(router.serializeUrl(result as UrlTree)).toBe('/onboarding/company');
  });

  it('allows authenticated users with tenant on /app/home', () => {
    setup({ authenticated: true, hasUser: true, hasTenant: true });
    const result = TestBed.runInInjectionContext(() => authGuard(mockRoute, makeState('/app/home')));

    expect(result).toBe(true);
  });

  it('redirects authenticated users with tenant away from /onboarding/company', () => {
    const { router } = setup({ authenticated: true, hasUser: true, hasTenant: true });
    const result = TestBed.runInInjectionContext(() => authGuard(mockRoute, makeState('/onboarding/company')));

    expect(router.serializeUrl(result as UrlTree)).toBe('/app/home');
  });

  it('redirects to /login when loadCurrentUser fails', async () => {
    const { router } = setup({
      authenticated: true,
      hasUser: false,
      loadUserResult: throwError(() => new Error('expired'))
    });

    const result$ = TestBed.runInInjectionContext(() =>
      authGuard(mockRoute, makeState('/app/home'))
    ) as Observable<boolean | UrlTree>;
    const resolved = await firstValueFrom(result$);

    expect(router.serializeUrl(resolved as UrlTree)).toBe('/login');
  });
});
