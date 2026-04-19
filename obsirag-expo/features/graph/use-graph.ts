import { useQuery } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';

export type GraphQueryFilters = {
  folders?: string[];
  tags?: string[];
  noteTypes?: string[];
  searchText?: string;
  recencyDays?: number;
};

export function useGraph(filters?: GraphQueryFilters) {
  const { api, backendUrl, useMockServer } = useServerConfig();

  return useQuery({
    queryKey: ['graph', backendUrl, useMockServer ? 'mock' : 'live', filters],
    queryFn: () => api.getGraph(filters),
    placeholderData: (previousData) => previousData,
  });
}

export function useGraphSubgraph(noteId?: string, depth = 1, filters?: GraphQueryFilters) {
  const { api, backendUrl, useMockServer } = useServerConfig();

  return useQuery({
    queryKey: ['graph', backendUrl, useMockServer ? 'mock' : 'live', 'subgraph', noteId, depth, filters],
    queryFn: () => api.getGraphSubgraph(noteId as string, depth, filters),
    enabled: Boolean(noteId),
    placeholderData: (previousData) => previousData,
  });
}
