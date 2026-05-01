import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

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

export function useSystemLogs(limit = 200) {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['system-logs', limit],
    queryFn: () => api.getLogs(limit),
    refetchInterval: 10000,
  });
}

export function useReindexData() {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.reindexData(),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['system-status'] }),
        queryClient.invalidateQueries({ queryKey: ['system-logs'] }),
      ]);
    },
  });
}
