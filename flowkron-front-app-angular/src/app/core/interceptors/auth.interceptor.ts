import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, switchMap, throwError } from 'rxjs';
import { AGENT_CORE_API_BASE_URL, API_BASE_URL, OPERATIONAL_API_BASE_URL } from '@core/config/api.config';
import { AuthService } from '@domains/auth/data-access/auth-api.service';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  const accessToken = auth.getAccessToken();
  const tenantId = auth.getTenantId();
  const isApiRequest = request.url.startsWith(API_BASE_URL);
  const isOperationalRequest = request.url.startsWith(OPERATIONAL_API_BASE_URL);
  const isAgentCoreRequest = request.url.startsWith(AGENT_CORE_API_BASE_URL);
  const shouldAttachAuth = isApiRequest || isOperationalRequest || isAgentCoreRequest;
  const isAuthRequest =
    request.url.includes('/auth/login/') ||
    request.url.includes('/auth/password/forgot/') ||
    request.url.includes('/auth/password/reset/') ||
    request.url.includes('/auth/email/confirm/');
  const isRefreshRequest = request.url.includes('/auth/refresh/');

  let headers = request.headers.set('X-Correlation-ID', crypto.randomUUID());

  if (shouldAttachAuth && accessToken && !isAuthRequest && !isRefreshRequest) {
    headers = headers.set('Authorization', `Bearer ${accessToken}`);
  }

  if (shouldAttachAuth && tenantId && !isAuthRequest && !isRefreshRequest) {
    headers = headers.set('X-Tenant-ID', String(tenantId));
  }

  const authRequest = request.clone({ headers });

  return next(authRequest).pipe(
    catchError((error: unknown) => {
      if (
        error instanceof HttpErrorResponse &&
            error.status === 401 &&
            shouldAttachAuth &&
            !isAuthRequest &&
            !isRefreshRequest
      ) {
        return auth.refreshSession().pipe(
          catchError((refreshError) => {
            auth.clearLocalSession();
            void router.navigate(['/login']);
            return throwError(() => refreshError);
          }),
          switchMap((tokens) => {
            const retryRequest = authRequest.clone({
              setHeaders: {
                Authorization: `Bearer ${tokens.access}`
              }
            });

            return next(retryRequest).pipe(
              catchError((retryError) => {
                if (!isOperationalRequest && !isAgentCoreRequest) {
                  auth.clearLocalSession();
                  void router.navigate(['/login']);
                }
                return throwError(() => retryError);
              })
            );
          })
        );
      }

      return throwError(() => error);
    })
  );
};
