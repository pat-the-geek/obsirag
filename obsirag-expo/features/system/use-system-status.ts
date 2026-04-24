import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';
import type { LogEntry } from '../../types/domain';

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

export function useSystemLogs(refetchIntervalMs = 4000) {
  const { api } = useServerConfig();

  return useQuery<LogEntry[]>({
    queryKey: ['system-logs'],
    queryFn: () => api.getLogs(200),
    refetchInterval: refetchIntervalMs,
  });
}

export function useReindexData() {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.reindexData(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['system-status'] });
    },
  });
}
