import { StyleSheet, Text, View } from 'react-native';

import { NoteDetail } from '../../types/domain';
import { MarkdownNote } from './markdown-note';
import { TagPill } from '../ui/tag-pill';

type NoteCardProps = {
  note: NoteDetail;
  onOpenNote?: (value: string) => void;
  onOpenTag?: (value: string) => void;
};

export function NoteCard({ note, onOpenNote, onOpenTag }: NoteCardProps) {
  return (
    <View style={styles.card}>
      <Text style={styles.title}>{note.title}</Text>
      <View style={styles.tagsRow}>
        {(note.tags || []).map((tag) => (
          <TagPill key={tag} label={tag} {...(onOpenTag ? { onPress: () => onOpenTag(tag) } : {})} />
        ))}
      </View>
      <View style={styles.metaRow}>
        {note.noteType ? <Text style={styles.metaText}>Type: {note.noteType}</Text> : null}
        {note.dateModified ? <Text style={styles.metaText}>Modifiee: {note.dateModified.slice(0, 10)}</Text> : null}
      </View>
      <MarkdownNote markdown={note.bodyMarkdown} {...(onOpenNote ? { onOpenNote } : {})} {...(onOpenTag ? { onOpenTag } : {})} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 18,
    backgroundColor: '#fffdfa',
    borderWidth: 1,
    borderColor: '#d8cfc0',
    padding: 16,
    gap: 12,
  },
  title: {
    fontSize: 22,
    fontWeight: '800',
    color: '#1f160c',
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
    color: '#6f5d49',
    fontSize: 12,
  },
});
