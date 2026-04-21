import { Redirect } from 'expo-router';

import { SystemStartupView } from '../components/system/system-startup-view';
import { Screen } from '../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../features/auth/use-server-config';
import { useStoreHydrated } from '../store/app-store';
import { useAppTheme } from '../theme/app-theme';

export default function IndexRoute() {
  const theme = useAppTheme();
  const hasHydrated = useStoreHydrated();
  const { backendUrl, useMockServer } = useServerConfig();
  const session = useSessionStatus();

  if (!hasHydrated) {
    return (
      <Screen backgroundColor={theme.colors.background}>
        <SystemStartupView loading />
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
      <Screen backgroundColor={theme.colors.background}>
        <SystemStartupView loading />
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
