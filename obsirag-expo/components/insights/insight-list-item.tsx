import { Pressable, StyleSheet, Text, View } from 'react-native';

import { InsightItem } from '../../types/domain';
import { StatusPill } from '../ui/status-pill';
import { TagPill } from '../ui/tag-pill';

type InsightListItemProps = {
  item: InsightItem;
  onPress?: () => void;
  onOpenTag?: (tag: string) => void;
};

export function InsightListItem({ item, onPress, onOpenTag }: InsightListItemProps) {
  return (
    <View style={styles.card}>
      <Pressable onPress={onPress} style={styles.mainPressable}>
        <View style={styles.header}>
          <Text style={styles.title}>{item.title}</Text>
          <StatusPill label={item.kind} tone="neutral" />
        </View>
        {item.excerpt ? <Text style={styles.excerpt}>{item.excerpt}</Text> : null}
        <Text style={styles.meta}>{item.filePath}</Text>
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
    backgroundColor: '#fffdfa',
    borderWidth: 1,
    borderColor: '#d8cfc0',
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
    color: '#1f160c',
    fontWeight: '700',
    fontSize: 16,
  },
  excerpt: {
    color: '#564733',
    lineHeight: 20,
  },
  tagsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  meta: {
    color: '#8a7760',
    fontSize: 12,
  },
});
