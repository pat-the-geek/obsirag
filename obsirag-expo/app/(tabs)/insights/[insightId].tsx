import { useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { NoteCard } from '../../../components/notes/note-card';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useInsightDetail } from '../../../features/insights/use-insights';

export default function InsightDetailScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ insightId: string }>();
  const insightId = useMemo(() => (Array.isArray(params.insightId) ? params.insightId[0] : params.insightId), [params.insightId]);
  const { data, isLoading, isRefetching, refetch } = useInsightDetail(insightId);

  if (!insightId || isLoading || !data) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      <NoteCard note={data} onOpenTag={(value) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(value)}`)} />
      <SectionCard title="Navigation" subtitle="Ouvre la note avec la route standard du visualiseur Expo.">
        <Pressable style={styles.button} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(data.filePath)}`)}>
          <Text style={styles.buttonText}>Ouvrir comme note</Text>
        </Pressable>
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#263e5f',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  buttonText: {
    color: '#f9f6f0',
    fontWeight: '700',
  },
});
