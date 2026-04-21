import { PropsWithChildren, Ref } from 'react';
import { NativeSyntheticEvent, NativeScrollEvent, RefreshControl, ScrollView, StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

import { useAppTheme } from '../../theme/app-theme';

type ScreenProps = PropsWithChildren<{
  scroll?: boolean;
  refreshing?: boolean;
  onRefresh?: () => void;
  backgroundColor?: string;
  contentStyle?: StyleProp<ViewStyle>;
  scrollContentStyle?: StyleProp<ViewStyle>;
  scrollRef?: Ref<ScrollView>;
  onScroll?: (event: NativeSyntheticEvent<NativeScrollEvent>) => void;
}>;

export function Screen({ children, scroll = true, refreshing = false, onRefresh, backgroundColor, contentStyle, scrollContentStyle, scrollRef, onScroll }: ScreenProps) {
  const insets = useSafeAreaInsets();
  const theme = useAppTheme();
  const content = <View style={[styles.content, contentStyle]}>{children}</View>;

  return (
    <SafeAreaView edges={['top', 'right', 'bottom', 'left']} style={[styles.safeArea, { backgroundColor: backgroundColor ?? theme.colors.background }, backgroundColor ? { backgroundColor } : null]}>
      {scroll ? (
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={[styles.scroll, { paddingBottom: 20 + insets.bottom }, scrollContentStyle]}
          refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.primary} /> : undefined}
          onScroll={onScroll}
          scrollEventThrottle={onScroll ? 16 : undefined}
        >
          {content}
        </ScrollView>
      ) : (
        content
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
  },
  scroll: {
    paddingBottom: 32,
  },
  content: {
    flexGrow: 1,
    paddingHorizontal: 18,
    paddingTop: 16,
    gap: 16,
  },
});
