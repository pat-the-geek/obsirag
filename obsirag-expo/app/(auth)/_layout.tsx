import { Redirect, Stack } from 'expo-router';
import { ActivityIndicator } from 'react-native';

import { Screen } from '../../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { useStoreHydrated } from '../../store/app-store';

export default function AuthLayout() {
  const hasHydrated = useStoreHydrated();
  const { backendUrl, useMockServer } = useServerConfig();
  const session = useSessionStatus();

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
