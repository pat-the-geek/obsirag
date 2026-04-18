import { Redirect, Stack, useSegments } from 'expo-router';
import { ActivityIndicator } from 'react-native';

import { Screen } from '../../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { useStoreHydrated } from '../../store/app-store';

function AuthGuardedLayout() {
  const session = useSessionStatus();

  if (session.isLoading) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  if (session.data?.authenticated) {
    return <Redirect href="/(tabs)" />;
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}

export default function AuthLayout() {
  const hasHydrated = useStoreHydrated();
  const segments = useSegments();
  const { backendUrl, useMockServer } = useServerConfig();
  const isServerConfigRoute = segments.includes('server-config');

  if (!hasHydrated) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  if (!backendUrl) {
    return <Stack screenOptions={{ headerShown: false }} />;
  }

  if (useMockServer) {
    return <Stack screenOptions={{ headerShown: false }} />;
  }

  if (isServerConfigRoute) {
    return <Stack screenOptions={{ headerShown: false }} />;
  }

  return <AuthGuardedLayout />;
}
