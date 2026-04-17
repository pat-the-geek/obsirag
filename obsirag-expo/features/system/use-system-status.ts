import { useQuery } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';

export function useSystemStatus() {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['system-status'],
    queryFn: () => api.getSystemStatus(),
    refetchInterval: 10000,
  });
}
