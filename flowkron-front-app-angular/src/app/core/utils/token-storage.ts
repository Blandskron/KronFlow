import { AuthTokenResponse } from '@domains/auth/domain/auth.model';

const ACCESS_TOKEN_KEY = 'flowkron.access_token';
const REFRESH_TOKEN_KEY = 'flowkron.refresh_token';
const TENANT_ID_KEY = 'flowkron.tenant_id';

export function readAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function readRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function readTenantId(): number | null {
  const raw = localStorage.getItem(TENANT_ID_KEY);
  return raw ? Number(raw) : null;
}

export function writeTokens(tokens: AuthTokenResponse, tenantId?: number | null): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
  writeTenantId(tenantId ?? null);
}

export function writeTenantId(tenantId: number | null): void {
  if (tenantId) {
    localStorage.setItem(TENANT_ID_KEY, String(tenantId));
    return;
  }
  localStorage.removeItem(TENANT_ID_KEY);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(TENANT_ID_KEY);
}
