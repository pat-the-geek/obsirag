import { useQuery } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';

type UseSystemStatusOptions = {
  refetchIntervalMs?: number;
};

export function useSystemStatus(options?: UseSystemStatusOptions) {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['system-status'],
    queryFn: () => api.getSystemStatus(),
    refetchInterval: options?.refetchIntervalMs ?? 10000,
  });
}
