import { ScrollView, StyleSheet, Text, View } from 'react-native';

import type { LogEntry } from '../../types/domain';

type LogConsoleProps = {
  entries: LogEntry[];
};

export function LogConsole({ entries }: LogConsoleProps) {
  if (!entries.length) {
    return (
      <View style={styles.emptyState}>
        <Text style={styles.emptyText}>Aucun log disponible.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {entries.map((entry, index) => (
        <View key={`${entry.timestamp}-${entry.level}-${index}`} style={styles.row}>
          <Text style={styles.meta}>{entry.timestamp} [{entry.level}] {entry.name}:{entry.line}</Text>
          <Text style={styles.message}>{entry.message}</Text>
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    maxHeight: 260,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#0f1115',
  },
  content: {
    padding: 12,
    gap: 10,
  },
  row: {
    gap: 4,
  },
  meta: {
    color: '#9bb4d3',
    fontSize: 11,
  },
  message: {
    color: '#e8edf6',
    fontSize: 12,
    lineHeight: 18,
  },
  emptyState: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    padding: 12,
  },
  emptyText: {
    color: '#6f5d49',
    fontSize: 12,
  },
});
