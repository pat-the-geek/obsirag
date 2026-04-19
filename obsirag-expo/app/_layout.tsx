import { Stack } from 'expo-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { loadAccessToken } from '../services/storage/secure-session';
import { useAppStore } from '../store/app-store';
import { useAppTheme } from '../theme/app-theme';

export default function RootLayout() {
  const [queryClient] = useState(() => new QueryClient());
  const setAccessToken = useAppStore((state) => state.setAccessToken);
  const theme = useAppTheme();

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
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <StatusBar style={theme.isDark ? 'light' : 'dark'} />
        <Stack screenOptions={{ headerShown: false }} />
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
