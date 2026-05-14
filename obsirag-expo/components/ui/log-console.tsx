import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { useAppTheme } from '../../theme/app-theme';
import type { LogEntry } from '../../types/domain';

type LogConsoleProps = {
  entries: LogEntry[];
};

export function LogConsole({ entries }: LogConsoleProps) {
  const { colors } = useAppTheme();

  if (!entries.length) {
    return (
      <View style={[styles.emptyState, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        <Text style={[styles.emptyText, { color: colors.textMuted }]}>Aucun log disponible.</Text>
      </View>
    );
  }

  return (
    <ScrollView style={[styles.container, { backgroundColor: colors.background, borderColor: colors.border }]} contentContainerStyle={styles.content}>
      {entries.map((entry, index) => (
        <View key={`${entry.timestamp}-${entry.level}-${index}`} style={styles.row}>
          <Text style={[styles.meta, { color: colors.textMuted }]}>{entry.timestamp} [{entry.level}] {entry.name}:{entry.line}</Text>
          <Text style={[styles.message, { color: colors.text }]}>{entry.message}</Text>
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
  },
  content: {
    padding: 12,
    gap: 10,
  },
  row: {
    gap: 4,
  },
  meta: {
    fontSize: 11,
  },
  message: {
    fontSize: 12,
    lineHeight: 18,
  },
  emptyState: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
  },
  emptyText: {
    fontSize: 12,
  },
});
