import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput } from 'react-native';
import { useRouter } from 'expo-router';

import { MetricStrip } from '../../components/system/metric-strip';
import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { StatusPill } from '../../components/ui/status-pill';
import { useNoteSearch } from '../../features/notes/use-notes';
import { useSystemStatus } from '../../features/system/use-system-status';

export default function DashboardScreen() {
  const router = useRouter();
  const [noteQuery, setNoteQuery] = useState('');
  const { data, isLoading, isRefetching, refetch } = useSystemStatus();
  const noteSearch = useNoteSearch(noteQuery);

  if (isLoading || !data) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      <MetricStrip
        items={[
          { label: 'Notes indexees', value: data.notesIndexed },
          { label: 'Chunks', value: data.chunksIndexed },
          { label: 'LLM', value: data.llmAvailable ? 'Disponible' : 'Hors ligne' },
        ]}
      />
      <SectionCard title="Etat du systeme" subtitle="Synthese rapide du runtime ObsiRAG expose par le backend.">
        <StatusPill label={data.backendReachable ? 'Backend joignable' : 'Backend indisponible'} tone={data.backendReachable ? 'success' : 'danger'} />
        <Text>Indexation: {data.indexing?.current ?? 'Etat inconnu'}</Text>
        <Text>Auto-learn: {data.autolearn?.step ?? 'Etat inconnu'}</Text>
      </SectionCard>
      <SectionCard title="Alertes" subtitle="Le backend peut pousser ici les alertes produit, perf ou indexation.">
        {(data.alerts ?? []).map((alert) => (
          <SectionCard key={alert.id} title={alert.title} subtitle={alert.description}>
            <StatusPill label={alert.level} tone={alert.level === 'error' ? 'danger' : alert.level === 'warning' ? 'warning' : 'neutral'} />
          </SectionCard>
        ))}
      </SectionCard>
      <SectionCard title="Acces rapides" subtitle="Recherche de note et navigation directe depuis le dashboard.">
        <TextInput
          value={noteQuery}
          onChangeText={setNoteQuery}
          placeholder="Rechercher une note"
          placeholderTextColor="#8a7760"
          style={styles.input}
        />
        {(noteSearch.data ?? []).slice(0, 6).map((item) => (
          <Pressable key={item.filePath} style={styles.quickResult} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(item.filePath)}`)}>
            <Text style={styles.quickTitle}>{item.title}</Text>
            <Text style={styles.quickMeta}>{item.filePath}</Text>
          </Pressable>
        ))}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: 1,
    borderColor: '#d8cfc0',
    borderRadius: 14,
    backgroundColor: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#1f160c',
  },
  quickResult: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#e0d5c7',
    backgroundColor: '#f8f3eb',
    padding: 12,
    gap: 4,
  },
  quickTitle: {
    color: '#1f160c',
    fontWeight: '700',
  },
  quickMeta: {
    color: '#6f5d49',
    fontSize: 12,
  },
});
