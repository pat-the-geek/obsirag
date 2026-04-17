import { Feather } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import { ActivityIndicator } from 'react-native';

import { Screen } from '../../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { useStoreHydrated } from '../../store/app-store';

export default function TabsLayout() {
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

  if (!useMockServer && session.isLoading) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  if (!useMockServer && !session.data?.authenticated) {
    return <Redirect href="/(auth)/login" />;
  }

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#a55233',
        tabBarInactiveTintColor: '#8a7760',
        tabBarStyle: {
          backgroundColor: '#fffdfa',
          borderTopColor: '#d8cfc0',
        },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Dashboard', tabBarIcon: ({ color, size }) => <Feather name="home" size={size} color={color} /> }} />
      <Tabs.Screen name="chat" options={{ title: 'Chat', popToTopOnBlur: true, tabBarIcon: ({ color, size }) => <Feather name="message-circle" size={size} color={color} /> }} />
      <Tabs.Screen name="insights" options={{ title: 'Insights', tabBarIcon: ({ color, size }) => <Feather name="layers" size={size} color={color} /> }} />
      <Tabs.Screen name="graph" options={{ title: 'Graphe', tabBarIcon: ({ color, size }) => <Feather name="share-2" size={size} color={color} /> }} />
      <Tabs.Screen name="settings" options={{ title: 'Settings', tabBarIcon: ({ color, size }) => <Feather name="settings" size={size} color={color} /> }} />
      <Tabs.Screen name="note/[noteId]" options={{ href: null }} />
    </Tabs>
  );
}
