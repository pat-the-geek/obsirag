import { StyleSheet, Text, View } from 'react-native';

type StatusPillProps = {
  label: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
};

export function StatusPill({ label, tone = 'neutral' }: StatusPillProps) {
  return (
    <View style={[styles.base, styles[tone]]}>
      <Text style={[styles.text, styles[`${tone}Text`]]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  text: {
    fontSize: 12,
    fontWeight: '700',
  },
  neutral: { backgroundColor: '#e8e1d6' },
  success: { backgroundColor: '#dcefd9' },
  warning: { backgroundColor: '#f6e5c6' },
  danger: { backgroundColor: '#f3d2d2' },
  neutralText: { color: '#55442e' },
  successText: { color: '#255b28' },
  warningText: { color: '#7a4f00' },
  dangerText: { color: '#7b1e1e' },
});
