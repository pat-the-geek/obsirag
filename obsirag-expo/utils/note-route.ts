type NoteRouteOptions = {
  returnTo?: string;
};

export function buildNoteRoute(notePath: string, options: NoteRouteOptions = {}): string {
  const encodedPath = encodeURIComponent(notePath);
  const baseRoute = `/(tabs)/note/${encodedPath}`;

  if (!options.returnTo) {
    return baseRoute;
  }

  return `${baseRoute}?returnTo=${encodeURIComponent(options.returnTo)}`;
}
