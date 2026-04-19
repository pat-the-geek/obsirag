import { Feather } from '@expo/vector-icons';
import type { EventArg } from '@react-navigation/native';
import { Redirect, Tabs, useRouter, useSegments } from 'expo-router';
import { ActivityIndicator } from 'react-native';

import { Screen } from '../../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { useAppStore, useStoreHydrated } from '../../store/app-store';

type TabBarIconProps = {
  color: string;
  size: number;
};

export default function TabsLayout() {
  const hasHydrated = useStoreHydrated();
  const router = useRouter();
  const routeSegments = useSegments() as readonly string[];
  const { backendUrl, useMockServer } = useServerConfig();
  const session = useSessionStatus();
  const setActiveConversationId = useAppStore((state) => state.setActiveConversationId);
  const isInsideChatThread = routeSegments.includes('chat') && routeSegments.length > 2;

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

  if (!useMockServer && session.isError) {
    return <Redirect href="/(auth)/server-config" />;
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
      <Tabs.Screen name="index" options={{ title: 'Dashboard', tabBarIcon: ({ color, size }: TabBarIconProps) => <Feather name="home" size={size} color={color} /> }} />
      <Tabs.Screen
        name="chat"
        listeners={{
          tabPress: (event: EventArg<'tabPress', true, undefined>) => {
            if (!isInsideChatThread) {
              return;
            }
            event.preventDefault();
            setActiveConversationId(undefined);
            router.replace('/(tabs)/chat');
          },
        }}
        options={{ title: 'Chat', popToTopOnBlur: true, tabBarIcon: ({ color, size }: TabBarIconProps) => <Feather name="message-circle" size={size} color={color} /> }}
      />
      <Tabs.Screen name="insights" options={{ title: 'Insights', tabBarIcon: ({ color, size }: TabBarIconProps) => <Feather name="layers" size={size} color={color} /> }} />
      <Tabs.Screen name="graph" options={{ title: 'Graphe', tabBarIcon: ({ color, size }: TabBarIconProps) => <Feather name="share-2" size={size} color={color} /> }} />
      <Tabs.Screen name="settings" options={{ title: 'Settings', tabBarIcon: ({ color, size }: TabBarIconProps) => <Feather name="settings" size={size} color={color} /> }} />
      <Tabs.Screen name="note/[noteId]" options={{ href: null }} />
    </Tabs>
  );
}
