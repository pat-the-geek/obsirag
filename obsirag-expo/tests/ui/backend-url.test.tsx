import { isLocalOnlyUrl, normalizeBackendUrlInput, resolveSessionBackendUrlHint } from '../../features/auth/backend-url';

describe('backend URL helpers', () => {
  it('normalizes missing and duplicated protocols', () => {
    expect(normalizeBackendUrlInput('100.65.216.90:8000')).toBe('http://100.65.216.90:8000');
    expect(normalizeBackendUrlInput('http://http://100.65.216.90:8000')).toBe('http://100.65.216.90:8000');
    expect(normalizeBackendUrlInput('https://https://example.com')).toBe('https://example.com');
    expect(normalizeBackendUrlInput('http://127.0.0.1:8000/server-config')).toBe('http://127.0.0.1:8000');
    expect(normalizeBackendUrlInput('https://example.com/api/v1')).toBe('https://example.com');
  });

  it('treats loopback and wildcard URLs as local-only', () => {
    expect(isLocalOnlyUrl('http://localhost:8000')).toBe(true);
    expect(isLocalOnlyUrl('http://127.0.0.1:8000')).toBe(true);
    expect(isLocalOnlyUrl('http://0.0.0.0:8000')).toBe(true);
    expect(isLocalOnlyUrl('http://192.168.1.50:8000')).toBe(false);
  });

  it('keeps an existing LAN backend URL when the backend hints localhost', () => {
    expect(resolveSessionBackendUrlHint('http://192.168.1.50:8000', 'http://localhost:8000')).toBeNull();
  });

  it('accepts a non-local backend hint', () => {
    expect(resolveSessionBackendUrlHint('http://localhost:8000', 'http://192.168.1.50:8000')).toBe('http://192.168.1.50:8000');
  });
});