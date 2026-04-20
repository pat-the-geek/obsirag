import { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';

import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { isLocalOnlyUrl, resolveLocalWebBackendUrl, resolveSessionBackendUrlHint } from '../../features/auth/backend-url';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { saveAccessToken } from '../../services/storage/secure-session';
import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';

export default function ServerConfigScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ allowStay?: string }>();
  const queryClient = useQueryClient();
  const theme = useAppTheme();
  const { scale } = useAppFontScale();
  const {
    api,
    backendUrl,
    accessToken,
    useMockServer,
    setBackendUrl,
    setAccessToken,
    setUseMockServer,
  } = useServerConfig();
  const session = useSessionStatus();
  const [pending, setPending] = useState(false);
  const allowStay = params.allowStay === '1';

  useEffect(() => {
    if (allowStay || pending || useMockServer) {
      return;
    }
    if (session.data?.authenticated) {
      router.replace('/(tabs)');
    }
  }, [allowStay, pending, router, session.data?.authenticated, useMockServer]);

  const onSave = async () => {
    setPending(true);
    try {
      if (useMockServer) {
        await saveAccessToken('');
        setAccessToken('');
        await queryClient.invalidateQueries();
        router.replace('/(tabs)');
        return;
      }

      const session = await api.createSession(accessToken);
      await saveAccessToken(accessToken);
      setUseMockServer(false);
      let nextBackendUrl = resolveSessionBackendUrlHint(backendUrl, session.backendUrlHint);
      if (
        typeof window !== 'undefined'
        && window.location?.origin
        && isLocalOnlyUrl(backendUrl)
        && nextBackendUrl
        && !isLocalOnlyUrl(nextBackendUrl)
      ) {
        nextBackendUrl = resolveLocalWebBackendUrl(nextBackendUrl, window.location.origin) ?? nextBackendUrl;
      }
      if (nextBackendUrl) {
        setBackendUrl(nextBackendUrl);
      }
      await queryClient.invalidateQueries();
      router.replace('/(tabs)');
    } catch (error) {
      Alert.alert('Connexion impossible', error instanceof Error ? error.message : 'Erreur inconnue');
    } finally {
      setPending(false);
    }
  };

  return (
    <Screen>
      <SectionCard title="Connexion backend" subtitle="Configurez l'instance ObsiRAG qui alimentera l'application Expo.">
        <Text style={[styles.label, { color: theme.colors.text, fontSize: scaleFontSize(14, scale) }]}>URL backend</Text>
        <TextInput value={backendUrl} onChangeText={setBackendUrl} style={[styles.input, { borderColor: theme.colors.border, backgroundColor: theme.colors.surface, color: theme.colors.text, fontSize: scaleFontSize(14, scale) }]} autoCapitalize="none" />
        <Text style={[styles.helpText, { color: theme.colors.textMuted, fontSize: scaleFontSize(13, scale), lineHeight: scaleLineHeight(20, scale) }]}>
          Sur Expo Go mobile, n'utilisez pas localhost. Renseignez l'IP reseau de cette machine pour le port 8000, ou activez le backend mock.
        </Text>
        <Text style={[styles.label, { color: theme.colors.text, fontSize: scaleFontSize(14, scale) }]}>Token d'acces</Text>
        <TextInput value={accessToken} onChangeText={setAccessToken} style={[styles.input, { borderColor: theme.colors.border, backgroundColor: theme.colors.surface, color: theme.colors.text, fontSize: scaleFontSize(14, scale) }]} autoCapitalize="none" secureTextEntry />
        <View style={styles.switchRow}>
          <Text style={[styles.switchLabel, { color: theme.colors.textMuted, fontSize: scaleFontSize(14, scale) }]}>Utiliser le backend mock</Text>
          <Switch value={useMockServer} onValueChange={setUseMockServer} />
        </View>
        <Pressable onPress={onSave} disabled={pending} style={[styles.button, { backgroundColor: theme.colors.primary }, pending && styles.buttonDisabled]}>
          <Text style={[styles.buttonText, { color: theme.colors.primaryText, fontSize: scaleFontSize(13, scale) }]}>{pending ? 'Verification...' : 'Enregistrer et continuer'}</Text>
        </Pressable>
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  label: {
    fontWeight: '700',
  },
  input: {
    borderWidth: 1,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  switchLabel: {
    flex: 1,
  },
  helpText: {
    lineHeight: 20,
  },
  button: {
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: 'center',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    fontWeight: '800',
  },
});
