import { Pressable, StyleSheet, Text, View } from 'react-native';

import { SourceRef } from '../../types/domain';

type SourceListProps = {
  sources?: SourceRef[];
  onSelectSource?: (source: SourceRef) => void;
  isOpen?: boolean;
  onToggleOpen?: () => void;
};

export function SourceList({ sources, onSelectSource, isOpen = false, onToggleOpen }: SourceListProps) {
  if (!sources?.length) {
    return null;
  }

  return (
    <View style={styles.container}>
      <Pressable testID="sources-panel-toggle" style={styles.header} onPress={onToggleOpen}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>Sources</Text>
          <Text style={styles.caption}>{sources.length} source{sources.length > 1 ? 's' : ''}</Text>
        </View>
        <Text style={styles.chevron}>{isOpen ? 'Masquer' : 'Afficher'}</Text>
      </Pressable>
      {isOpen ? (
        <View testID="sources-panel-content" style={styles.content}>
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
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
    borderRadius: 16,
    backgroundColor: '#fbf8f3',
    borderWidth: 1,
    borderColor: '#ded5c9',
    padding: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  headerCopy: {
    gap: 2,
  },
  title: {
    fontSize: 13,
    fontWeight: '700',
    color: '#3a2c1f',
  },
  caption: {
    fontSize: 12,
    color: '#7a6855',
  },
  chevron: {
    color: '#8a562b',
    fontSize: 12,
    fontWeight: '700',
  },
  content: {
    gap: 8,
  },
  item: {
    padding: 12,
    borderRadius: 14,
    backgroundColor: '#fffdfa',
    borderWidth: 1,
    borderColor: '#ded5c9',
  },
  itemTitle: {
    color: '#2f2419',
    fontWeight: '700',
  },
  itemMeta: {
    color: '#7a6855',
    fontSize: 12,
    marginTop: 4,
  },
});
