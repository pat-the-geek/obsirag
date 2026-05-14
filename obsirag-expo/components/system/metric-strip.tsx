import { StyleSheet, Text, View } from 'react-native';

import { useAppTheme } from '../../theme/app-theme';

type MetricStripProps = {
  items: Array<{ label: string; value: string | number }>;
};

export function MetricStrip({ items }: MetricStripProps) {
  const { colors } = useAppTheme();
  return (
    <View style={styles.row}>
      {items.map((item) => (
        <View key={item.label} style={[styles.item, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.value, { color: colors.text }]}>{item.value}</Text>
          <Text style={[styles.label, { color: colors.textMuted }]}>{item.label}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  item: {
    minWidth: 140,
    flexGrow: 1,
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
    gap: 4,
  },
  value: {
    fontSize: 24,
    fontWeight: '800',
  },
  label: {
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
});
