import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ConversationSummary } from '../../types/domain';
import { StatusPill } from '../ui/status-pill';

type ConversationListItemProps = {
  item: ConversationSummary;
  onPress: () => void;
  onDelete?: () => void;
  deleteDisabled?: boolean;
};

export function ConversationListItem({ item, onPress, onDelete, deleteDisabled = false }: ConversationListItemProps) {
  return (
    <View style={styles.card}>
      <Pressable onPress={onPress} style={styles.pressableContent}>
        <View style={styles.header}>
          <Text style={styles.title}>{item.title}</Text>
          {item.isCurrent ? <StatusPill label="Actif" tone="success" /> : null}
        </View>
        <Text style={styles.preview} numberOfLines={2}>
          {item.preview}
        </Text>
        <Text style={styles.meta}>
          {item.turnCount} tours · {item.messageCount} messages
        </Text>
      </Pressable>
      {onDelete ? (
        <Pressable onPress={onDelete} style={[styles.deleteButton, deleteDisabled ? styles.deleteButtonDisabled : null]} disabled={deleteDisabled}>
          <Text style={[styles.deleteButtonText, deleteDisabled ? styles.deleteButtonTextDisabled : null]}>{deleteDisabled ? 'Suppression...' : 'Supprimer'}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#fffdfa',
    overflow: 'hidden',
  },
  pressableContent: {
    padding: 14,
    gap: 8,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  title: {
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    color: '#1f160c',
  },
  preview: {
    color: '#544632',
    lineHeight: 20,
  },
  meta: {
    color: '#8a7760',
    fontSize: 12,
  },
  deleteButton: {
    borderTopWidth: 1,
    borderTopColor: '#eadfce',
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: '#f8efe6',
  },
  deleteButtonDisabled: {
    opacity: 0.6,
  },
  deleteButtonText: {
    color: '#9f4f2d',
    fontWeight: '700',
  },
  deleteButtonTextDisabled: {
    color: '#8f7e70',
  },
});
