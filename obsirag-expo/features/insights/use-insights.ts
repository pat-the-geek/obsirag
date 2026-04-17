import { useQuery } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';

export function useInsights() {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['insights'],
    queryFn: () => api.getInsights(),
  });
}

export function useInsightDetail(insightId?: string) {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['insight', insightId],
    queryFn: () => api.getInsight(insightId as string),
    enabled: Boolean(insightId),
  });
}
