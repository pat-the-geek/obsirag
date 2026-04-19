import { Pressable, StyleSheet, Text, View } from 'react-native';

import { InsightItem } from '../../types/domain';
import { useAppTheme } from '../../theme/app-theme';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';
import { StatusPill } from '../ui/status-pill';
import { TagPill } from '../ui/tag-pill';

type InsightListItemProps = {
  item: InsightItem;
  onPress?: () => void;
  onOpenTag?: (tag: string) => void;
};

export function InsightListItem({ item, onPress, onOpenTag }: InsightListItemProps) {
  const theme = useAppTheme();
  const metadata = joinMetadataParts([
    item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
    formatSizeBytes(item.sizeBytes),
  ]);

  return (
    <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }] }>
      <Pressable onPress={onPress} style={styles.mainPressable}>
        <View style={styles.header}>
          <Text style={[styles.title, { color: theme.colors.text }]}>{item.title}</Text>
          <StatusPill label={item.kind} tone="neutral" />
        </View>
        {item.excerpt ? <Text style={[styles.excerpt, { color: theme.colors.textMuted }]}>{item.excerpt}</Text> : null}
        <Text style={[styles.meta, { color: theme.colors.textSubtle }]}>{item.filePath}</Text>
        {metadata ? <Text style={[styles.meta, { color: theme.colors.textSubtle }]}>{metadata}</Text> : null}
      </Pressable>
      {item.tags.length ? (
        <View style={styles.tagsRow}>
          {item.tags.map((tag) => (
            <TagPill key={`${item.id}-${tag}`} label={tag} {...(onOpenTag ? { onPress: () => onOpenTag(tag) } : {})} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
    gap: 8,
  },
  mainPressable: {
    gap: 8,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
  },
  title: {
    flex: 1,
    fontWeight: '700',
    fontSize: 16,
  },
  excerpt: {
    lineHeight: 20,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  meta: {
    fontSize: 12,
  },
});
