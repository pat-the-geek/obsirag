import { Alert, Pressable, StyleSheet, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { useQueryClient } from '@tanstack/react-query';

import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { StatusPill } from '../../components/ui/status-pill';
import { useServerConfig, useSessionStatus } from '../../features/auth/use-server-config';
import { clearAccessToken } from '../../services/storage/secure-session';
import { useSystemStatus } from '../../features/system/use-system-status';

export default function SettingsScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { backendUrl, useMockServer, accessToken, setAccessToken, setUseMockServer } = useServerConfig();
  const { data, refetch, isRefetching } = useSystemStatus();
  const session = useSessionStatus();

  const onLogout = async () => {
    await clearAccessToken();
    setAccessToken('');
    await queryClient.invalidateQueries({ queryKey: ['session'] });
    Alert.alert('Session effacee', 'Le token local a ete supprime de l\'app Expo.');
    router.replace('/(auth)/login');
  };

  const onSwitchToMock = async () => {
    setUseMockServer(true);
    await queryClient.invalidateQueries();
  };

  const autolearnLabel = useMockServer
    ? 'Worker mock'
    : data?.autolearn?.running
      ? data.autolearn.managedBy === 'worker'
        ? 'Worker separe actif'
        : 'Auto-learner actif'
      : data?.autolearn?.managedBy === 'worker'
        ? 'Worker separe inactif'
        : 'Auto-learner inactif';

  const autolearnTone = useMockServer
    ? 'warning'
    : data?.autolearn?.running
      ? 'success'
      : 'neutral';

  return (
    <Screen refreshing={isRefetching || session.isRefetching} onRefresh={() => { void refetch(); void session.refetch(); }}>
      <SectionCard title="Configuration serveur" subtitle="Le frontend est deja structure pour un backend Python expose via API REST/SSE.">
        <Text>Backend: {backendUrl}</Text>
        <StatusPill label={useMockServer ? 'Mode mock' : 'Mode live'} tone={useMockServer ? 'warning' : 'success'} />
        <Pressable onPress={() => router.push('/(auth)/server-config')} style={styles.button}>
          <Text style={styles.buttonText}>Modifier la connexion</Text>
        </Pressable>
        {!useMockServer ? (
          <Pressable onPress={onSwitchToMock} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Basculer en mock</Text>
          </Pressable>
        ) : null}
      </SectionCard>
      <SectionCard title="Session" subtitle="Etat de la session backend et gestion locale du token. Rechargement par pull-to-refresh.">
        <StatusPill
          label={useMockServer ? 'Session mock' : session.data?.authenticated ? 'Session valide' : 'Session non verifiee'}
          tone={useMockServer ? 'warning' : session.data?.authenticated ? 'success' : 'danger'}
        />
        <Text>Mode: {session.data?.mode ?? (useMockServer ? 'mock' : 'inconnu')}</Text>
        <Text>Auth requise: {session.data?.requiresAuth ? 'oui' : 'non'}</Text>
        <Text>Token local: {accessToken ? 'present' : 'absent'}</Text>
        <Text>Preview token: {session.data?.tokenPreview ?? '-'}</Text>
        {!useMockServer ? (
          <Pressable onPress={() => { void session.refetch(); }} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Verifier la session</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={() => { void onLogout(); }} style={styles.dangerButton}>
          <Text style={styles.buttonText}>Effacer la session</Text>
        </Pressable>
      </SectionCard>
      <SectionCard title="Runtime visible">
        <Text>LLM: {data?.llmAvailable ? 'disponible' : 'indisponible'}</Text>
        <Text>Notes indexees: {data?.notesIndexed ?? '-'}</Text>
        <Text>Chunks: {data?.chunksIndexed ?? '-'}</Text>
        <StatusPill label={autolearnLabel} tone={autolearnTone} />
        <Text>Gestion auto-learn: {data?.autolearn?.managedBy ?? '-'}</Text>
        <Text>PID worker: {data?.autolearn?.pid ?? '-'}</Text>
        <Text>Etape: {data?.autolearn?.step ?? '-'}</Text>
        <Text>Debut worker: {formatTimestamp(data?.autolearn?.startedAt)}</Text>
        <Text>Derniere maj: {formatTimestamp(data?.autolearn?.updatedAt)}</Text>
        <Text>Prochain cycle: {formatTimestamp(data?.autolearn?.nextRunAt)}</Text>
      </SectionCard>
    </Screen>
  );
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('fr-FR');
}

const styles = StyleSheet.create({
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#263e5f',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#e8ddd0',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    color: '#3d2e20',
    fontWeight: '700',
  },
  dangerButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#a55233',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  buttonText: {
    color: '#f9f6f0',
    fontWeight: '700',
  },
});
