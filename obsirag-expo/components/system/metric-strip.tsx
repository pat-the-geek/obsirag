import { StyleSheet, Text, View } from 'react-native';

type MetricStripProps = {
  items: Array<{ label: string; value: string | number }>;
};

export function MetricStrip({ items }: MetricStripProps) {
  return (
    <View style={styles.row}>
      {items.map((item) => (
        <View key={item.label} style={styles.item}>
          <Text style={styles.value}>{item.value}</Text>
          <Text style={styles.label}>{item.label}</Text>
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
    backgroundColor: '#fffdfa',
    borderWidth: 1,
    borderColor: '#d8cfc0',
    padding: 14,
    gap: 4,
  },
  value: {
    fontSize: 24,
    fontWeight: '800',
    color: '#1f160c',
  },
  label: {
    color: '#6c5a44',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
});
