import { useEffect, useMemo } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { NoteCard } from '../../../components/notes/note-card';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useNoteDetail } from '../../../features/notes/use-notes';
import { useAppTheme } from '../../../theme/app-theme';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../../utils/format-display';
import { buildNoteRoute, getCanonicalNotePath } from '../../../utils/note-route';

export default function NoteScreen() {
  const router = useRouter();
  const theme = useAppTheme();
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
        <Pressable
          testID="note-return-button"
          style={[styles.returnButton, { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted }]}
          onPress={() => router.replace(returnTo)}
        >
          <Text style={[styles.returnButtonLabel, { color: theme.colors.text }]}>Retour à la conversation</Text>
        </Pressable>
      ) : null}
      <NoteCard
        note={data}
        onOpenNote={openNoteFromCurrentContext}
        onOpenTag={(value) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(value)}`)}
      />
      <SectionCard title="Retrolinks">
        {data.backlinks.map((item) => (
          <Pressable key={item.filePath} style={[styles.linkCard, { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted }]} onPress={() => openNoteFromCurrentContext(item.filePath)}>
            <Text style={[styles.linkTitle, { color: theme.colors.text }]}>{item.title}</Text>
            <Text style={[styles.linkMeta, { color: theme.colors.textMuted }]}>{item.filePath}</Text>
            {joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ]) ? (
              <Text style={[styles.linkMeta, { color: theme.colors.textMuted }] }>
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
          <Pressable key={item.filePath} style={[styles.linkCard, { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted }]} onPress={() => openNoteFromCurrentContext(item.filePath)}>
            <Text style={[styles.linkTitle, { color: theme.colors.text }]}>{item.title}</Text>
            <Text style={[styles.linkMeta, { color: theme.colors.textMuted }]}>{item.filePath}</Text>
            {joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ]) ? (
              <Text style={[styles.linkMeta, { color: theme.colors.textMuted }] }>
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
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  returnButtonLabel: {
    fontWeight: '700',
  },
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
