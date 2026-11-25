import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';
import { Observable, catchError, map, of } from 'rxjs';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

export const noAuthGuard: CanActivateFn = (): boolean | UrlTree | Observable<boolean | UrlTree> => {
  const auth = inject(AuthService);
  const router = inject(Router);

  if (!auth.isAuthenticated()) {
    return true;
  }

  if (auth.currentUser()) {
    return router.createUrlTree([auth.currentTenant() ? '/app/home' : '/onboarding/company']);
  }

  return auth.loadCurrentUser().pipe(
    map(() => router.createUrlTree([auth.currentTenant() ? '/app/home' : '/onboarding/company'])),
    catchError(() => {
      auth.clearLocalSession();
      return of(true);
    })
  );
};
