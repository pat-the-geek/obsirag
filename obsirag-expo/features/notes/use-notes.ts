import { useQuery } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';

export function useNoteDetail(noteId?: string) {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['note', noteId],
    queryFn: () => api.getNote(noteId as string),
    enabled: Boolean(noteId),
  });
}

export function useNoteSearch(query?: string) {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['note-search', query],
    queryFn: () => api.searchNotes((query ?? '').trim()),
    enabled: Boolean(query?.trim()),
  });
}
