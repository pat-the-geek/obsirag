import { useEffect, useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { NoteCard } from '../../../components/notes/note-card';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useNoteDetail } from '../../../features/notes/use-notes';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../../utils/format-display';
import { buildNoteRoute, getCanonicalNotePath } from '../../../utils/note-route';

export default function NoteScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ noteId: string }>();
  const noteId = useMemo(() => (Array.isArray(params.noteId) ? params.noteId[0] : params.noteId), [params.noteId]);
  const { data, isLoading, isRefetching, refetch } = useNoteDetail(noteId);

  useEffect(() => {
    const currentPath = getCanonicalNotePath(noteId);
    if (data?.filePath && currentPath && currentPath !== data.filePath) {
      router.replace(buildNoteRoute(data.filePath));
    }
  }, [data?.filePath, noteId, router]);

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
        onOpenNote={(value) => router.push(buildNoteRoute(value))}
        onOpenTag={(value) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(value)}`)}
      />
      <SectionCard title="Retrolinks">
        {data.backlinks.map((item) => (
          <Pressable key={item.filePath} style={styles.linkCard} onPress={() => router.push(buildNoteRoute(item.filePath))}>
            <Text style={styles.linkTitle}>{item.title}</Text>
            <Text style={styles.linkMeta}>{item.filePath}</Text>
            {joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ]) ? (
              <Text style={styles.linkMeta}>
                {joinMetadataParts([
                  item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
                  formatSizeBytes(item.sizeBytes),
                ])}
              </Text>
            ) : null}
          </Pressable>
        ))}
      </SectionCard>
      <SectionCard title="Liens sortants">
        {data.links.map((item) => (
          <Pressable key={item.filePath} style={styles.linkCard} onPress={() => router.push(buildNoteRoute(item.filePath))}>
            <Text style={styles.linkTitle}>{item.title}</Text>
            <Text style={styles.linkMeta}>{item.filePath}</Text>
            {joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ]) ? (
              <Text style={styles.linkMeta}>
                {joinMetadataParts([
                  item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
                  formatSizeBytes(item.sizeBytes),
                ])}
              </Text>
            ) : null}
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
