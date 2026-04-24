import { useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Feather } from '@expo/vector-icons';

import type { LogEntry } from '../../types/domain';
import { useAppTheme } from '../../theme/app-theme';

type Props = {
  entries: LogEntry[];
};

const LEVEL_COLORS: Record<string, string> = {
  DEBUG: '#6b7280',
  INFO: '#9ca3af',
  WARNING: '#f59e0b',
  ERROR: '#ef4444',
  CRITICAL: '#dc2626',
};

function levelColor(level: string): string {
  return LEVEL_COLORS[level] ?? '#9ca3af';
}

export function LogConsole({ entries }: Props) {
  const theme = useAppTheme();
  const scrollRef = useRef<ScrollView>(null);
  const [filter, setFilter] = useState('');

  const filtered = filter.trim()
    ? entries.filter((e) => {
        const q = filter.toLowerCase();
        return e.message.toLowerCase().includes(q) || e.name.toLowerCase().includes(q) || e.level.toLowerCase().includes(q);
      })
    : entries;

  useEffect(() => {
    scrollRef.current?.scrollToEnd({ animated: false });
  }, [filtered.length]);

  return (
    <View style={styles.root}>
      <View style={[styles.searchRow, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
        <Feather name="search" size={14} color={theme.colors.textMuted} style={styles.searchIcon} />
        <TextInput
          value={filter}
          onChangeText={setFilter}
          placeholder="Filtrer les logs…"
          placeholderTextColor={theme.colors.textMuted}
          style={[styles.searchInput, { color: theme.colors.text }]}
          clearButtonMode="while-editing"
        />
      </View>
      <ScrollView
        ref={scrollRef}
        style={[styles.console, { backgroundColor: '#0d1117', borderColor: theme.colors.border }]}
        contentContainerStyle={styles.consoleContent}
      >
        {filtered.length === 0 ? (
          <Text style={styles.empty}>Aucun log disponible.</Text>
        ) : (
          filtered.map((entry, i) => (
            <View key={i} style={styles.row}>
              <Text style={[styles.ts, { color: '#6b7280' }]}>
                {entry.timestamp.slice(11, 19)}
              </Text>
              <Text style={[styles.level, { color: levelColor(entry.level) }]}>
                {entry.level.slice(0, 4)}
              </Text>
              <Text style={[styles.name, { color: '#60a5fa' }]} numberOfLines={1}>
                {entry.name.split('.').pop()}
              </Text>
              <Text style={[styles.msg, { color: '#e5e7eb' }]} selectable>
                {entry.message}
              </Text>
            </View>
          ))
        )}
      </ScrollView>
      <Text style={[styles.count, { color: theme.colors.textMuted }]}>
        {filtered.length} / {entries.length} entrées
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    gap: 8,
  },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 6,
    gap: 6,
  },
  searchIcon: {
    flexShrink: 0,
  },
  searchInput: {
    flex: 1,
    fontSize: 13,
    padding: 0,
    margin: 0,
  },
  console: {
    height: 320,
    borderWidth: 1,
    borderRadius: 10,
  },
  consoleContent: {
    padding: 10,
    gap: 2,
  },
  empty: {
    color: '#6b7280',
    fontSize: 12,
    fontStyle: 'italic',
  },
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    alignItems: 'flex-start',
  },
  ts: {
    fontSize: 11,
    fontFamily: 'monospace',
    flexShrink: 0,
  },
  level: {
    fontSize: 11,
    fontFamily: 'monospace',
    fontWeight: '700',
    flexShrink: 0,
    width: 32,
  },
  name: {
    fontSize: 11,
    fontFamily: 'monospace',
    flexShrink: 0,
    maxWidth: 100,
  },
  msg: {
    fontSize: 11,
    fontFamily: 'monospace',
    flex: 1,
    flexShrink: 1,
  },
  count: {
    fontSize: 11,
    textAlign: 'right',
  },
});
