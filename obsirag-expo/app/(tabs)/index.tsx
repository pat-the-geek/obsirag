import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
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
  const logScrollRef = useRef<ScrollView | null>(null);
  const autolearnLog = data?.autolearn?.log ?? [];

  useEffect(() => {
    logScrollRef.current?.scrollToEnd({ animated: false });
  }, [autolearnLog]);

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
      <SectionCard title="Journal auto-learn" subtitle="Flux runtime de l'auto-learner, avec les derniers evenements visibles en bas.">
        <View style={styles.logFrame}>
          <ScrollView
            ref={logScrollRef}
            style={styles.logScroll}
            contentContainerStyle={styles.logContent}
            nestedScrollEnabled
            showsVerticalScrollIndicator={false}
            onContentSizeChange={() => {
              logScrollRef.current?.scrollToEnd({ animated: false });
            }}
          >
            {autolearnLog.length ? (
              autolearnLog.map((entry, index) => (
                <Text key={`${index}-${entry}`} style={styles.logEntry}>
                  {entry}
                </Text>
              ))
            ) : (
              <Text style={styles.logEmpty}>Aucun evenement auto-learn a afficher.</Text>
            )}
          </ScrollView>
        </View>
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
  logFrame: {
    minHeight: 220,
    maxHeight: 260,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#d9cfbe',
    backgroundColor: '#201812',
    overflow: 'hidden',
  },
  logScroll: {
    flex: 1,
  },
  logContent: {
    flexGrow: 1,
    justifyContent: 'flex-end',
    paddingHorizontal: 14,
    paddingVertical: 14,
    gap: 8,
  },
  logEntry: {
    color: '#ece3d5',
    fontSize: 13,
    lineHeight: 19,
    fontFamily: 'Menlo',
  },
  logEmpty: {
    color: '#b8aa95',
    fontSize: 13,
    lineHeight: 19,
    fontStyle: 'italic',
  },
});
