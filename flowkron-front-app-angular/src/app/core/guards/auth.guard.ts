import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';
import { Observable, catchError, map, of } from 'rxjs';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

export const authGuard: CanActivateFn = (_route, state): boolean | UrlTree | Observable<boolean | UrlTree> => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  if (auth.currentUser()) {
    return resolveAuthenticatedRoute(auth, router, state.url);
  }

  return auth.loadCurrentUser().pipe(
    map(() => resolveAuthenticatedRoute(auth, router, state.url)),
    catchError(() => of(router.createUrlTree(['/login'])))
  );
};

function resolveAuthenticatedRoute(auth: AuthService, router: Router, url: string): boolean | UrlTree {
  const isOnboardingRoute = url.startsWith('/onboarding/company');
  const hasTenant = Boolean(auth.currentTenant());

  if (!hasTenant && !isOnboardingRoute) {
    return router.createUrlTree(['/onboarding/company']);
  }

  if (hasTenant && isOnboardingRoute) {
    return router.createUrlTree(['/app/home']);
  }

  return true;
}
