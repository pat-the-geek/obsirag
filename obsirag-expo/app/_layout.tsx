import { Stack } from 'expo-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';

import { loadAccessToken } from '../services/storage/secure-session';
import { useAppStore } from '../store/app-store';

export default function RootLayout() {
  const [queryClient] = useState(() => new QueryClient());
  const setAccessToken = useAppStore((state) => state.setAccessToken);

  useEffect(() => {
    let active = true;

    loadAccessToken()
      .then((token) => {
        if (active && token) {
          setAccessToken(token);
        }
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [setAccessToken]);

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerShown: false }} />
    </QueryClientProvider>
  );
}
