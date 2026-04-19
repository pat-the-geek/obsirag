import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ConversationSummary } from '../../types/domain';
import { useAppTheme } from '../../theme/app-theme';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';
import { StatusPill } from '../ui/status-pill';

type ConversationListItemProps = {
  item: ConversationSummary;
  onPress: () => void;
  onDelete?: () => void;
  deleteDisabled?: boolean;
};

export function ConversationListItem({ item, onPress, onDelete, deleteDisabled = false }: ConversationListItemProps) {
  const theme = useAppTheme();
  const metadata = joinMetadataParts([
    item.updatedAt ? `Modifie le ${formatMetadataDate(item.updatedAt)}` : null,
    formatSizeBytes(item.sizeBytes),
    `${item.turnCount} tours`,
    `${item.messageCount} messages`,
  ]);

  return (
    <View style={[styles.card, { borderColor: theme.colors.border, backgroundColor: theme.colors.surface }] }>
      <Pressable onPress={onPress} style={styles.pressableContent}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: theme.colors.text }]}>{item.title}</Text>
          {item.isCurrent ? <StatusPill label="Actif" tone="success" /> : null}
        </View>
        <Text style={[styles.preview, { color: theme.colors.textMuted }]} numberOfLines={2}>
          {item.preview}
        </Text>
        <Text style={[styles.meta, { color: theme.colors.textSubtle }]}>{metadata}</Text>
      </Pressable>
      {onDelete ? (
        <Pressable onPress={onDelete} style={[styles.deleteButton, { borderTopColor: theme.colors.border, backgroundColor: theme.colors.backgroundAlt }, deleteDisabled ? styles.deleteButtonDisabled : null]} disabled={deleteDisabled}>
          <Text style={[styles.deleteButtonText, { color: theme.colors.danger }, deleteDisabled ? [styles.deleteButtonTextDisabled, { color: theme.colors.textSubtle }] : null]}>{deleteDisabled ? 'Suppression...' : 'Supprimer'}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderWidth: 1,
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
  },
  preview: {
    lineHeight: 20,
  },
  meta: {
    fontSize: 12,
  },
  deleteButton: {
    borderTopWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  deleteButtonDisabled: {
    opacity: 0.6,
  },
  deleteButtonText: {
    fontWeight: '700',
  },
  deleteButtonTextDisabled: {
  },
});
