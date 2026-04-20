import { Stack } from 'expo-router';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Component, ReactNode, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { resolveLocalWebBackendUrl } from '../features/auth/backend-url';
import { loadAccessToken } from '../services/storage/secure-session';
import { useAppStore } from '../store/app-store';
import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../theme/app-theme';

type RootErrorBoundaryProps = {
  children: ReactNode;
};

type RootErrorBoundaryState = {
  hasError: boolean;
};

class RootErrorBoundary extends Component<RootErrorBoundaryProps, RootErrorBoundaryState> {
  state: RootErrorBoundaryState = {
    hasError: false,
  };

  static getDerivedStateFromError(): RootErrorBoundaryState {
    return { hasError: true };
  }

  override componentDidCatch(error: unknown): void {
    console.error('ObsiRAG Expo root startup failed.', error);
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      return <RootFallbackShell mode="error" />;
    }

    return this.props.children;
  }
}

function RootFallbackShell({ mode }: { mode: 'loading' | 'error' }) {
  const { scale } = useAppFontScale();
  return (
    <View style={styles.rootShell}>
      <View style={styles.rootCard}>
        <Text style={[styles.eyebrow, { fontSize: scaleFontSize(12, scale) }]}>ObsiRAG</Text>
        <Text style={[styles.title, { fontSize: scaleFontSize(28, scale) }]}>{mode === 'error' ? 'Demarrage interrompu' : 'Demarrage en cours'}</Text>
        <Text style={[styles.copy, { fontSize: scaleFontSize(15, scale), lineHeight: scaleLineHeight(22, scale) }]}>
          {mode === 'error'
            ? 'Une erreur est survenue pendant l\'initialisation de l\'application web. Rechargez la page pour reprendre le bootstrap.'
            : 'Initialisation du client web, du store local et de la session avant ouverture de l\'application.'}
        </Text>
        {mode === 'loading' ? <ActivityIndicator size="small" color="#a55233" /> : null}
      </View>
    </View>
  );
}

function RootLayoutContent() {
  const [queryClient] = useState(() => new QueryClient());
  const [tokenBootstrapComplete, setTokenBootstrapComplete] = useState(false);
  const backendUrl = useAppStore((state) => state.backendUrl);
  const setAccessToken = useAppStore((state) => state.setAccessToken);
  const setBackendUrl = useAppStore((state) => state.setBackendUrl);
  const theme = useAppTheme();

  useEffect(() => {
    if (typeof document !== 'undefined') {
      document.body?.setAttribute('data-obsirag-booted', 'true');
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.location?.origin) {
      return;
    }

    const recoveredBackendUrl = resolveLocalWebBackendUrl(backendUrl, window.location.origin);
    if (recoveredBackendUrl) {
      setBackendUrl(recoveredBackendUrl);
    }
  }, [backendUrl, setBackendUrl]);

  useEffect(() => {
    let active = true;

    Promise.resolve()
      .then(() => loadAccessToken())
      .then((token) => {
        if (active && token) {
          setAccessToken(token);
        }
      })
      .catch((error) => {
        console.error('Unable to restore persisted access token.', error);
      })
      .finally(() => {
        if (active) {
          setTokenBootstrapComplete(true);
        }
      });

    return () => {
      active = false;
    };
  }, [setAccessToken]);

  if (!tokenBootstrapComplete) {
    return <RootFallbackShell mode="loading" />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <StatusBar style={theme.isDark ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false }} />
    </QueryClientProvider>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <RootErrorBoundary>
        <RootLayoutContent />
      </RootErrorBoundary>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  rootShell: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
    backgroundColor: '#f4f1ea',
  },
  rootCard: {
    width: '100%',
    maxWidth: 560,
    borderRadius: 24,
    paddingHorizontal: 24,
    paddingVertical: 28,
    gap: 12,
    backgroundColor: '#fffaf1',
    borderWidth: 1,
    borderColor: '#e2d3bd',
  },
  eyebrow: {
    color: '#8a562b',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  title: {
    color: '#1f160c',
    fontSize: 28,
    fontWeight: '800',
  },
  copy: {
    color: '#5f4f3c',
    fontSize: 15,
    lineHeight: 22,
  },
});
