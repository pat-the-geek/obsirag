import { StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, useAppFontScale, useAppTheme } from '../../theme/app-theme';

type StatusPillProps = {
  label: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
};

export function StatusPill({ label, tone = 'neutral' }: StatusPillProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();
  const toneStyle = {
    neutral: { backgroundColor: theme.colors.neutralSurface, color: theme.colors.neutralText },
    success: { backgroundColor: theme.colors.successSurface, color: theme.colors.successText },
    warning: { backgroundColor: theme.colors.warningSurface, color: theme.colors.warningText },
    danger: { backgroundColor: theme.colors.dangerSurface, color: theme.colors.dangerPillText },
  }[tone];

  return (
    <View style={[styles.base, { backgroundColor: toneStyle.backgroundColor }]}>
      <Text style={[styles.text, { color: toneStyle.color, fontSize: scaleFontSize(12, scale) }]}>{label}</Text>
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
});
