import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { ObsiRagApi } from '../../services/api/obsirag-api';
import { useAppStore, useStoreHydrated } from '../../store/app-store';

export function useServerConfig() {
  const backendUrl = useAppStore((state) => state.backendUrl);
  const accessToken = useAppStore((state) => state.accessToken);
  const useMockServer = useAppStore((state) => state.useMockServer);
  const setBackendUrl = useAppStore((state) => state.setBackendUrl);
  const setAccessToken = useAppStore((state) => state.setAccessToken);
  const setUseMockServer = useAppStore((state) => state.setUseMockServer);

  const api = useMemo(
    () =>
      new ObsiRagApi({
        backendUrl,
        accessToken,
        useMockServer,
      }),
    [accessToken, backendUrl, useMockServer],
  );

  return {
    api,
    backendUrl,
    accessToken,
    useMockServer,
    setBackendUrl,
    setAccessToken,
    setUseMockServer,
  };
}

export function useSessionStatus() {
  const { api, useMockServer } = useServerConfig();
  const hasHydrated = useStoreHydrated();
  const backendUrl = useAppStore((state) => state.backendUrl);
  const accessToken = useAppStore((state) => state.accessToken);

  return useQuery({
    queryKey: ['session', backendUrl, accessToken, useMockServer ? 'mock' : 'live'],
    queryFn: () => api.getSession(),
    retry: false,
    enabled: hasHydrated && !useMockServer && Boolean(backendUrl),
  });
}
