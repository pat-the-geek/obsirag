import { useState } from 'react';
import { Alert, Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';

import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { useServerConfig } from '../../features/auth/use-server-config';
import { saveAccessToken } from '../../services/storage/secure-session';

export default function ServerConfigScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const {
    api,
    backendUrl,
    accessToken,
    useMockServer,
    setBackendUrl,
    setAccessToken,
    setUseMockServer,
  } = useServerConfig();
  const [pending, setPending] = useState(false);

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
      if (session.backendUrlHint && session.backendUrlHint !== backendUrl) {
        setBackendUrl(session.backendUrlHint);
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
        <Text style={styles.label}>URL backend</Text>
        <TextInput value={backendUrl} onChangeText={setBackendUrl} style={styles.input} autoCapitalize="none" />
        <Text style={styles.label}>Token d'acces</Text>
        <TextInput value={accessToken} onChangeText={setAccessToken} style={styles.input} autoCapitalize="none" secureTextEntry />
        <View style={styles.switchRow}>
          <Text style={styles.switchLabel}>Utiliser le backend mock</Text>
          <Switch value={useMockServer} onValueChange={setUseMockServer} />
        </View>
        <Pressable onPress={onSave} disabled={pending} style={[styles.button, pending && styles.buttonDisabled]}>
          <Text style={styles.buttonText}>{pending ? 'Verification...' : 'Enregistrer et continuer'}</Text>
        </Pressable>
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  label: {
    fontWeight: '700',
    color: '#1f160c',
  },
  input: {
    borderWidth: 1,
    borderColor: '#d8cfc0',
    borderRadius: 14,
    backgroundColor: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#1f160c',
  },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  switchLabel: {
    flex: 1,
    color: '#4f402d',
  },
  button: {
    borderRadius: 999,
    backgroundColor: '#a55233',
    paddingVertical: 14,
    alignItems: 'center',
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: '#fff8ef',
    fontWeight: '800',
  },
});
