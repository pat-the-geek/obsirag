import { useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { NoteCard } from '../../../components/notes/note-card';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useNoteDetail } from '../../../features/notes/use-notes';
import { useAppTheme } from '../../../theme/app-theme';

export default function NoteScreen() {
  const router = useRouter();
  const { colors } = useAppTheme();
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
          <Pressable
            key={item.filePath}
            style={[styles.linkCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]}
            onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(item.filePath)}`)}
          >
            <Text style={[styles.linkTitle, { color: colors.text }]}>{item.title}</Text>
            <Text style={[styles.linkMeta, { color: colors.textMuted }]}>{item.filePath}</Text>
          </Pressable>
        ))}
      </SectionCard>
      <SectionCard title="Liens sortants">
        {data.links.map((item) => (
          <Pressable
            key={item.filePath}
            style={[styles.linkCard, { backgroundColor: colors.surfaceMuted, borderColor: colors.border }]}
            onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(item.filePath)}`)}
          >
            <Text style={[styles.linkTitle, { color: colors.text }]}>{item.title}</Text>
            <Text style={[styles.linkMeta, { color: colors.textMuted }]}>{item.filePath}</Text>
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
    padding: 12,
    gap: 4,
  },
  linkTitle: {
    fontWeight: '700',
  },
  linkMeta: {
    fontSize: 12,
  },
});
