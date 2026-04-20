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
  const params = useLocalSearchParams<{ noteId: string; returnTo?: string }>();
  const noteId = useMemo(() => (Array.isArray(params.noteId) ? params.noteId[0] : params.noteId), [params.noteId]);
  const returnTo = useMemo(
    () => (Array.isArray(params.returnTo) ? params.returnTo[0] : params.returnTo) || '',
    [params.returnTo],
  );
  const { data, isLoading, isRefetching, refetch } = useNoteDetail(noteId);

  const openNoteFromCurrentContext = (value: string) => {
    router.push(buildNoteRoute(value, returnTo ? { returnTo } : undefined));
  };

  useEffect(() => {
    const currentPath = getCanonicalNotePath(noteId);
    if (data?.filePath && currentPath && currentPath !== data.filePath) {
      router.replace(buildNoteRoute(data.filePath, returnTo ? { returnTo } : undefined));
    }
  }, [data?.filePath, noteId, returnTo, router]);

  if (!noteId || isLoading || !data) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      {returnTo ? (
        <Pressable testID="note-return-button" style={styles.returnButton} onPress={() => router.replace(returnTo)}>
          <Text style={styles.returnButtonLabel}>Retour à la conversation</Text>
        </Pressable>
      ) : null}
      <NoteCard
        note={data}
        onOpenNote={openNoteFromCurrentContext}
        onOpenTag={(value) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(value)}`)}
      />
      <SectionCard title="Retrolinks">
        {data.backlinks.map((item) => (
          <Pressable key={item.filePath} style={styles.linkCard} onPress={() => openNoteFromCurrentContext(item.filePath)}>
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
          <Pressable key={item.filePath} style={styles.linkCard} onPress={() => openNoteFromCurrentContext(item.filePath)}>
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
  returnButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  returnButtonLabel: {
    color: '#1f160c',
    fontWeight: '700',
  },
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
