import { Pressable, StyleSheet, Text, View } from 'react-native';

import { buildAppTheme, useAppTheme } from '../../theme/app-theme';

type TagPillProps = {
  label: string;
  onPress?: () => void;
  tone?: 'light' | 'dark';
};

export function TagPill({ label, onPress, tone }: TagPillProps) {
  const appTheme = useAppTheme();
  const { colors } = tone ? buildAppTheme(tone) : appTheme;

  const content = (
    <>
      <Text style={[styles.hash, { color: colors.tagPillText }]}>#</Text>
      <Text style={[styles.text, { color: colors.tagPillText }]}>{label}</Text>
    </>
  );

  if (onPress) {
    return (
      <Pressable testID="tag-pill" style={[styles.base, { backgroundColor: colors.tagBackground }]} onPress={onPress}>
        {content}
      </Pressable>
    );
  }

  return <View style={[styles.base, { backgroundColor: colors.tagBackground }]}>{content}</View>;
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
  hash: {
    fontSize: 12,
    fontWeight: '800',
  },
  text: {
    fontSize: 12,
    fontWeight: '700',
  },
});
