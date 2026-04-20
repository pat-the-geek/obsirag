import { isLocalOnlyUrl, normalizeBackendUrlInput, resolveLocalWebBackendUrl, resolveSessionBackendUrlHint } from '../../features/auth/backend-url';

describe('backend URL helpers', () => {
  it('normalizes missing and duplicated protocols', () => {
    expect(normalizeBackendUrlInput('100.65.216.90:8000')).toBe('http://100.65.216.90:8000');
    expect(normalizeBackendUrlInput('http://http://100.65.216.90:8000')).toBe('http://100.65.216.90:8000');
    expect(normalizeBackendUrlInput('https://https://example.com')).toBe('https://example.com');
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

  it('recovers a stale non-local backend URL when the web app is served locally', () => {
    expect(resolveLocalWebBackendUrl('http://100.65.216.90:8000', 'http://127.0.0.1:8000')).toBe('http://127.0.0.1:8000');
  });

  it('does not rewrite a backend URL when the browser origin is not local', () => {
    expect(resolveLocalWebBackendUrl('http://100.65.216.90:8000', 'https://obsirag.example.com')).toBeNull();
  });
});