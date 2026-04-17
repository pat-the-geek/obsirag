import { Redirect, Stack, useSegments } from 'expo-router';
import { ActivityIndicator } from 'react-native';

import { Screen } from '../../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { useStoreHydrated } from '../../store/app-store';

export default function AuthLayout() {
  const hasHydrated = useStoreHydrated();
  const segments = useSegments();
  const { backendUrl, useMockServer } = useServerConfig();
  const session = useSessionStatus();
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

  if (session.isError) {
    if (isServerConfigRoute) {
      return <Stack screenOptions={{ headerShown: false }} />;
    }
    return <Redirect href="/(auth)/server-config" />;
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}
