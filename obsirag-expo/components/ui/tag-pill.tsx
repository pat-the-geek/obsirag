import { Pressable, StyleSheet, Text, View } from 'react-native';

type TagPillProps = {
  label: string;
  onPress?: () => void;
  tone?: 'light' | 'dark';
};

export function TagPill({ label, onPress, tone = 'light' }: TagPillProps) {
  const content = (
    <>
      <Text style={[styles.hash, tone === 'dark' ? styles.hashDark : styles.hashLight]}>#</Text>
      <Text style={[styles.text, tone === 'dark' ? styles.textDark : styles.textLight]}>{label}</Text>
    </>
  );

  if (onPress) {
    return (
      <Pressable testID="tag-pill" style={[styles.base, tone === 'dark' ? styles.baseDark : styles.baseLight]} onPress={onPress}>
        {content}
      </Pressable>
    );
  }

  return <View style={[styles.base, tone === 'dark' ? styles.baseDark : styles.baseLight]}>{content}</View>;
}

const styles = StyleSheet.create({
  base: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  baseLight: {
    backgroundColor: '#d8ebff',
  },
  baseDark: {
    backgroundColor: '#27425c',
  },
  hash: {
    fontSize: 12,
    fontWeight: '800',
  },
  hashLight: {
    color: '#315b7d',
  },
  hashDark: {
    color: '#a9d0f4',
  },
  text: {
    fontSize: 12,
    fontWeight: '700',
  },
  textLight: {
    color: '#17324a',
  },
  textDark: {
    color: '#e7f2ff',
  },
});