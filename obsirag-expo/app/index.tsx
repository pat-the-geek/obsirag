import { Redirect } from 'expo-router';
import { ActivityIndicator } from 'react-native';

import { Screen } from '../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../features/auth/use-server-config';
import { useStoreHydrated } from '../store/app-store';

export default function IndexRoute() {
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
    return <Redirect href="/(auth)/server-config" />;
  }

  if (useMockServer) {
    return <Redirect href="/(tabs)" />;
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
    return <Redirect href="/(auth)/server-config" />;
  }

  return <Redirect href="/(auth)/server-config" />;
}
