import { Pressable, StyleSheet, Text, View } from 'react-native';

import { InsightItem } from '../../types/domain';
import { StatusPill } from '../ui/status-pill';

type InsightListItemProps = {
  item: InsightItem;
  onPress?: () => void;
};

export function InsightListItem({ item, onPress }: InsightListItemProps) {
  return (
    <Pressable onPress={onPress} style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{item.title}</Text>
        <StatusPill label={item.kind} tone="neutral" />
      </View>
      {item.excerpt ? <Text style={styles.excerpt}>{item.excerpt}</Text> : null}
      <Text style={styles.meta}>{item.filePath}</Text>
    </Pressable>
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
  meta: {
    color: '#8a7760',
    fontSize: 12,
  },
});
