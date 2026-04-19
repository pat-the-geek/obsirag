export function buildNoteRoute(notePath: string) {
  return `/(tabs)/note/${encodeURIComponent(notePath)}`;
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