import { StyleSheet, Text, View } from 'react-native';

import { NoteDetail } from '../../types/domain';
import { useAppTheme } from '../../theme/app-theme';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';
import { MarkdownNote } from './markdown-note';
import { TagPill } from '../ui/tag-pill';

type NoteCardProps = {
  note: NoteDetail;
  onOpenNote?: (value: string) => void;
  onOpenTag?: (value: string) => void;
};

export function NoteCard({ note, onOpenNote, onOpenTag }: NoteCardProps) {
  const theme = useAppTheme();
  const metadata = joinMetadataParts([
    note.noteType ? `Type: ${note.noteType}` : null,
    note.dateModified ? `Modifie le ${formatMetadataDate(note.dateModified)}` : null,
    formatSizeBytes(note.sizeBytes),
  ]);

  return (
    <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }] }>
      <Text style={[styles.title, { color: theme.colors.text }]}>{note.title}</Text>
      <Text style={[styles.path, { color: theme.colors.textSubtle }]}>{note.filePath}</Text>
      <View style={styles.tagsRow}>
        {(note.tags || []).map((tag) => (
          <TagPill key={tag} label={tag} {...(onOpenTag ? { onPress: () => onOpenTag(tag) } : {})} />
        ))}
      </View>
      {metadata ? (
        <View style={styles.metaRow}>
          <Text style={[styles.metaText, { color: theme.colors.textMuted }]}>{metadata}</Text>
        </View>
      ) : null}
      <MarkdownNote markdown={note.bodyMarkdown} {...(onOpenNote ? { onOpenNote } : {})} {...(onOpenTag ? { onOpenTag } : {})} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 18,
    borderWidth: 1,
    padding: 16,
    gap: 12,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
  },
  path: {
    fontSize: 12,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  metaText: {
    fontSize: 12,
  },
});
