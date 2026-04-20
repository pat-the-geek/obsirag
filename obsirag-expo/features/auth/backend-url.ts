const LOCAL_ONLY_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1', '0.0.0.0']);

export function normalizeBackendUrlInput(value: string): string {
  let normalizedValue = value.trim();

  while (/^https?:\/\/https?:\/\//i.test(normalizedValue)) {
    normalizedValue = normalizedValue.replace(/^(https?:\/\/)(https?:\/\/)/i, '$2');
  }

  if (!normalizedValue) {
    return normalizedValue;
  }

  if (!/^[a-z][a-z0-9+.-]*:\/\//i.test(normalizedValue)) {
    normalizedValue = `http://${normalizedValue}`;
  }

  return normalizedValue.replace(/\/$/, '');
}

export function isLocalOnlyUrl(value: string): boolean {
  const normalizedValue = normalizeBackendUrlInput(value);
  if (!normalizedValue) {
    return false;
  }

  try {
    const url = new URL(normalizedValue);
    return LOCAL_ONLY_HOSTNAMES.has(url.hostname);
  } catch {
    return false;
  }
}

export function resolveSessionBackendUrlHint(currentBackendUrl: string, backendUrlHint?: string | null): string | null {
  const normalizedCurrentUrl = normalizeBackendUrlInput(currentBackendUrl);
  const normalizedHint = normalizeBackendUrlInput(backendUrlHint ?? '');

  if (!normalizedHint || normalizedHint === normalizedCurrentUrl) {
    return null;
  }

  if (isLocalOnlyUrl(normalizedHint) && normalizedCurrentUrl && !isLocalOnlyUrl(normalizedCurrentUrl)) {
    return null;
  }

  return normalizedHint;
}

export function resolveLocalWebBackendUrl(currentBackendUrl: string, browserOrigin?: string | null): string | null {
  const normalizedCurrentUrl = normalizeBackendUrlInput(currentBackendUrl);
  const normalizedBrowserOrigin = normalizeBackendUrlInput(browserOrigin ?? '');

  if (!normalizedCurrentUrl || !normalizedBrowserOrigin || normalizedCurrentUrl === normalizedBrowserOrigin) {
    return null;
  }

  if (!isLocalOnlyUrl(normalizedBrowserOrigin) || isLocalOnlyUrl(normalizedCurrentUrl)) {
    return null;
  }

  return normalizedBrowserOrigin;
}