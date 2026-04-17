import { PropsWithChildren } from 'react';
import { StyleSheet, Text, View } from 'react-native';

type SectionCardProps = PropsWithChildren<{
  title: string;
  subtitle?: string;
  headerAccessory?: React.ReactNode;
}>;

export function SectionCard({ children, title, subtitle, headerAccessory }: SectionCardProps) {
  return (
    <View style={styles.card}>
      <View style={styles.headerRow}>
        <View style={styles.titleBlock}>
          <Text style={styles.title}>{title}</Text>
          {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
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
    backgroundColor: '#fffdfa',
    borderWidth: 1,
    borderColor: '#d8cfc0',
    padding: 16,
    gap: 10,
    shadowColor: '#47331a',
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
