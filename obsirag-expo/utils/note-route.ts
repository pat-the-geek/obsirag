type NoteRouteOptions = {
  returnTo?: string;
};

export function buildNoteRoute(notePath: string, options?: NoteRouteOptions) {
  const encodedPath = encodeURIComponent(notePath);
  const returnTo = options?.returnTo?.trim();
  if (!returnTo) {
    return `/(tabs)/note/${encodedPath}`;
  }
  return `/(tabs)/note/${encodedPath}?returnTo=${encodeURIComponent(returnTo)}`;
}

export function getCanonicalNotePath(value: string | null | undefined) {
  if (!value) {
    return '';
  }

  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}