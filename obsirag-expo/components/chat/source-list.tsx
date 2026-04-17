import { Pressable, StyleSheet, Text, View } from 'react-native';

import { SourceRef } from '../../types/domain';

type SourceListProps = {
  sources?: SourceRef[];
  onSelectSource?: (source: SourceRef) => void;
};

export function SourceList({ sources, onSelectSource }: SourceListProps) {
  if (!sources?.length) {
    return null;
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Sources</Text>
      {sources.map((source) => (
        <Pressable
          key={`${source.filePath}-${source.noteTitle}`}
          style={styles.item}
          onPress={onSelectSource ? () => onSelectSource(source) : undefined}
        >
          <Text style={styles.itemTitle}>{source.noteTitle}</Text>
          <Text style={styles.itemMeta}>{source.filePath}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: '#cfcfcf',
  },
  item: {
    padding: 12,
    borderRadius: 14,
    backgroundColor: '#242424',
    borderWidth: 1,
    borderColor: '#343434',
  },
  itemTitle: {
    color: '#f3f3f3',
    fontWeight: '700',
  },
  itemMeta: {
    color: '#9e9e9e',
    fontSize: 12,
    marginTop: 4,
  },
});
