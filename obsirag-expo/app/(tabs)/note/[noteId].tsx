import { useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { NoteCard } from '../../../components/notes/note-card';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useNoteDetail } from '../../../features/notes/use-notes';

export default function NoteScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ noteId: string }>();
  const noteId = useMemo(() => (Array.isArray(params.noteId) ? params.noteId[0] : params.noteId), [params.noteId]);
  const { data, isLoading, isRefetching, refetch } = useNoteDetail(noteId);

  if (!noteId || isLoading || !data) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      <NoteCard
        note={data}
        onOpenNote={(value) => router.push(`/(tabs)/note/${encodeURIComponent(value)}`)}
        onOpenTag={(value) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(value)}`)}
      />
      <SectionCard title="Retrolinks">
        {data.backlinks.map((item) => (
          <Pressable key={item.filePath} style={styles.linkCard} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(item.filePath)}`)}>
            <Text style={styles.linkTitle}>{item.title}</Text>
            <Text style={styles.linkMeta}>{item.filePath}</Text>
          </Pressable>
        ))}
      </SectionCard>
      <SectionCard title="Liens sortants">
        {data.links.map((item) => (
          <Pressable key={item.filePath} style={styles.linkCard} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(item.filePath)}`)}>
            <Text style={styles.linkTitle}>{item.title}</Text>
            <Text style={styles.linkMeta}>{item.filePath}</Text>
          </Pressable>
        ))}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  linkCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    padding: 12,
    gap: 4,
  },
  linkTitle: {
    color: '#1f160c',
    fontWeight: '700',
  },
  linkMeta: {
    color: '#6f5d49',
    fontSize: 12,
  },
});
