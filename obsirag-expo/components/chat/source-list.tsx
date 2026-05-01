import { useMemo } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useAppTheme } from '../../theme/app-theme';
import { SourceRef } from '../../types/domain';

type SourceListProps = {
  sources?: SourceRef[];
  onSelectSource?: (source: SourceRef) => void;
  isOpen?: boolean;
  onToggleOpen?: () => void;
};

export function SourceList({ sources, onSelectSource, isOpen = false, onToggleOpen }: SourceListProps) {
  const theme = useAppTheme();
  const uniqueSources = useMemo(() => dedupeSources(sources), [sources]);

  if (!uniqueSources.length) {
    return null;
  }

  return (
    <View style={[styles.container, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
      <Pressable testID="sources-panel-toggle" style={styles.header} onPress={onToggleOpen}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, { color: theme.colors.text }]}>Sources</Text>
          <Text style={[styles.caption, { color: theme.colors.textMuted }]}>{uniqueSources.length} source{uniqueSources.length > 1 ? 's' : ''}</Text>
        </View>
        <Text style={[styles.chevron, { color: theme.colors.primary }]}>{isOpen ? 'Masquer' : 'Afficher'}</Text>
      </Pressable>
      {isOpen ? (
        <View testID="sources-panel-content" style={styles.content}>
          {uniqueSources.map((source) => (
            <Pressable
              key={`${source.filePath}-${source.noteTitle}`}
              style={[styles.item, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}
              onPress={onSelectSource ? () => onSelectSource(source) : undefined}
            >
              <Text style={[styles.itemTitle, { color: theme.colors.text }]}>{source.noteTitle}</Text>
              <Text style={[styles.itemMeta, { color: theme.colors.textMuted }]}>{source.filePath}</Text>
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
    borderWidth: 1,
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
  },
  caption: {
    fontSize: 12,
  },
  chevron: {
    fontSize: 12,
    fontWeight: '700',
  },
  content: {
    gap: 8,
  },
  item: {
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
  },
  itemTitle: {
    fontWeight: '700',
  },
  itemMeta: {
    fontSize: 12,
    marginTop: 4,
  },
});

function dedupeSources(sources?: SourceRef[]): SourceRef[] {
  if (!sources?.length) {
    return [];
  }

  const deduped = new Map<string, SourceRef>();
  for (const source of sources) {
    const key = sourceIdentityKey(source);
    if (!key) {
      continue;
    }
    const current = deduped.get(key);
    if (!current) {
      deduped.set(key, source);
      continue;
    }
    const mergedSource: SourceRef = {
      filePath: current.filePath || source.filePath,
      noteTitle: current.noteTitle || source.noteTitle || source.filePath || current.filePath,
      isPrimary: Boolean(current.isPrimary || source.isPrimary),
    };
    const mergedDateModified = current.dateModified || source.dateModified;
    if (mergedDateModified) {
      mergedSource.dateModified = mergedDateModified;
    }
    const mergedScore = mergeScore(current.score, source.score);
    if (typeof mergedScore === 'number') {
      mergedSource.score = mergedScore;
    }
    deduped.set(key, mergedSource);
  }

  return Array.from(deduped.values());
}

function sourceIdentityKey(source: SourceRef): string {
  const normalizedPath = normalizeSourcePath(source.filePath);
  const noteTitle = (source.noteTitle || '').trim().toLowerCase().replace(/\s+/g, ' ');
  if (normalizedPath && noteTitle) {
    return `${normalizedPath}|${noteTitle}`;
  }
  if (normalizedPath) {
    return normalizedPath;
  }
  if (noteTitle) {
    return `title:${noteTitle}`;
  }
  return '';
}

function normalizeSourcePath(filePath: string): string {
  return (filePath || '').trim().replace(/\\/g, '/').replace(/^\.\//, '').toLowerCase();
}

function mergeScore(current?: number, incoming?: number): number | undefined {
  if (typeof current === 'number' && typeof incoming === 'number') {
    return Math.max(current, incoming);
  }
  if (typeof current === 'number') {
    return current;
  }
  if (typeof incoming === 'number') {
    return incoming;
  }
  return undefined;
}
