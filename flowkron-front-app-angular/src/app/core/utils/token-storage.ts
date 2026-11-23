import { AuthTokenResponse } from '@domains/auth/domain/auth.model';

const ACCESS_TOKEN_KEY = 'flowkron.access_token';
const REFRESH_TOKEN_KEY = 'flowkron.refresh_token';
const TENANT_ID_KEY = 'flowkron.tenant_id';

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage no disponible o cuota excedida
  }
}

function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Storage no disponible
  }
}

export function readAccessToken(): string | null {
  return safeGet(ACCESS_TOKEN_KEY);
}

export function readRefreshToken(): string | null {
  return safeGet(REFRESH_TOKEN_KEY);
}

export function readTenantId(): number | null {
  const raw = safeGet(TENANT_ID_KEY);
  return raw ? Number(raw) : null;
}

export function writeTokens(tokens: AuthTokenResponse, tenantId?: number | null): void {
  safeSet(ACCESS_TOKEN_KEY, tokens.access);
  safeSet(REFRESH_TOKEN_KEY, tokens.refresh);
  writeTenantId(tenantId ?? null);
}

export function writeTenantId(tenantId: number | null): void {
  if (tenantId) {
    safeSet(TENANT_ID_KEY, String(tenantId));
    return;
  }
  safeRemove(TENANT_ID_KEY);
}

export function clearTokens(): void {
  safeRemove(ACCESS_TOKEN_KEY);
  safeRemove(REFRESH_TOKEN_KEY);
  safeRemove(TENANT_ID_KEY);
}
