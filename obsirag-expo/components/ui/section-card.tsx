import { PropsWithChildren } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, useAppFontScale, useAppTheme } from '../../theme/app-theme';

type SectionCardProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
  headerAccessory?: React.ReactNode;
}>;

export function SectionCard({ children, title, subtitle, headerAccessory }: SectionCardProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();

  return (
    <View style={[styles.card, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border, shadowColor: theme.colors.shadow }]}>
      <View style={styles.headerRow}>
        <View style={styles.titleBlock}>
          <Text style={[styles.title, { color: theme.colors.text, fontSize: scaleFontSize(18, scale) }]}>{title}</Text>
          {subtitle ? <Text style={[styles.subtitle, { color: theme.colors.textMuted, fontSize: scaleFontSize(13, scale) }]}>{subtitle}</Text> : null}
        </View>
        {headerAccessory ? <View style={styles.headerAccessory}>{headerAccessory}</View> : null}
      </View>
      <View style={styles.body}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    position: 'relative',
    overflow: 'visible',
    borderRadius: 18,
    borderWidth: 1,
    padding: 16,
    gap: 10,
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  headerRow: {
    position: 'relative',
    zIndex: 20,
    overflow: 'visible',
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    flexWrap: 'wrap',
  },
  titleBlock: {
    gap: 4,
    flexShrink: 1,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1f160c',
  },
  subtitle: {
    fontSize: 13,
    color: '#6b5b47',
  },
  headerAccessory: {
    flexShrink: 1,
    zIndex: 30,
    overflow: 'visible',
  },
  body: {
    position: 'relative',
    zIndex: 1,
    gap: 10,
  },
});
