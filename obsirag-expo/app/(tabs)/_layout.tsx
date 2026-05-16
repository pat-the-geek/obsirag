import { Home, Layers, MessageCircle, Settings, Share2 } from 'lucide-react-native';
import { Redirect, Tabs, useRouter, useSegments } from 'expo-router';
import { ActivityIndicator, Platform } from 'react-native';

import { useAppTheme } from '../../theme/app-theme';

import { Screen } from '../../components/ui/screen';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { useAppStore, useStoreHydrated } from '../../store/app-store';

export default function TabsLayout() {
  const { colors } = useAppTheme();
  const hasHydrated = useStoreHydrated();
  const router = useRouter();
  const routeSegments = useSegments() as readonly string[];
  const { backendUrl, useMockServer } = useServerConfig();
  const session = useSessionStatus();
  const setActiveConversationId = useAppStore((state) => state.setActiveConversationId);
  const isInsideChatThread = routeSegments.includes('chat') && routeSegments.length > 2;
  const standalonePwaWeb = isStandalonePwaWeb();

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
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.textMuted,
        ...(standalonePwaWeb ? { safeAreaInsets: { bottom: 0, left: 0, right: 0, top: 0 } } : {}),
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          ...(standalonePwaWeb
            ? {
                position: 'absolute',
                left: 0,
                right: 0,
                bottom: 0,
                height: 64,
                minHeight: 64,
                maxHeight: 64,
                paddingBottom: 0,
                paddingTop: 0,
              }
            : {}),
        },
        ...(standalonePwaWeb ? { tabBarItemStyle: { paddingVertical: 0, marginVertical: 0 } } : {}),
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Dashboard', tabBarIcon: ({ color, size }) => <Home size={size} color={color} /> }} />
      <Tabs.Screen
        name="chat"
        listeners={{
          tabPress: (event) => {
            if (!isInsideChatThread) {
              return;
            }
            event.preventDefault();
            setActiveConversationId(undefined);
            router.replace('/(tabs)/chat');
          },
        }}
        options={{ title: 'Chat', popToTopOnBlur: true, tabBarIcon: ({ color, size }) => <MessageCircle size={size} color={color} /> }}
      />
      <Tabs.Screen name="insights" options={{ title: 'Insights', tabBarIcon: ({ color, size }) => <Layers size={size} color={color} /> }} />
      <Tabs.Screen name="graph" options={{ title: 'Graphe', tabBarIcon: ({ color, size }) => <Share2 size={size} color={color} /> }} />
      <Tabs.Screen name="settings" options={{ title: 'Réglages', tabBarIcon: ({ color, size }) => <Settings size={size} color={color} /> }} />
      <Tabs.Screen name="note/[noteId]" options={{ href: null }} />
    </Tabs>
  );
}

function isStandalonePwaWeb() {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return false;
  }
  const byDisplayMode = window.matchMedia?.('(display-mode: standalone)')?.matches;
  const byNavigatorFlag = (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
  return Boolean(byDisplayMode || byNavigatorFlag);
}
