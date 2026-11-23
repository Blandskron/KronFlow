import {
  clearTokens,
  readAccessToken,
  readRefreshToken,
  readTenantId,
  writeTenantId,
  writeTokens
} from './token-storage';

describe('token-storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores and reads access, refresh, and tenant id', () => {
    writeTokens({ access: 'acc-1', refresh: 'ref-1' }, 42);

    expect(readAccessToken()).toBe('acc-1');
    expect(readRefreshToken()).toBe('ref-1');
    expect(readTenantId()).toBe(42);
  });

  it('removes tenant id when set to null', () => {
    writeTenantId(99);
    expect(readTenantId()).toBe(99);

    writeTenantId(null);
    expect(readTenantId()).toBeNull();
  });

  it('clears all stored auth keys', () => {
    writeTokens({ access: 'acc-2', refresh: 'ref-2' }, 7);
    clearTokens();

    expect(readAccessToken()).toBeNull();
    expect(readRefreshToken()).toBeNull();
    expect(readTenantId()).toBeNull();
  });
});
