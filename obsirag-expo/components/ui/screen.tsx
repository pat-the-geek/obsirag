import { PropsWithChildren, Ref } from 'react';
import { Platform, RefreshControl, ScrollView, StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
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
}>;

export function Screen({ children, scroll = true, refreshing = false, onRefresh, backgroundColor, contentStyle, scrollContentStyle, scrollRef }: ScreenProps) {
  const insets = useSafeAreaInsets();
  const theme = useAppTheme();
  const bottomPadding = insets.bottom + (isStandalonePwaWeb() ? 0 : 20);
  const content = <View style={[styles.content, contentStyle]}>{children}</View>;

  return (
    <SafeAreaView edges={['top', 'right', 'bottom', 'left']} style={[styles.safeArea, { backgroundColor: backgroundColor ?? theme.colors.background }, backgroundColor ? { backgroundColor } : null]}>
      {scroll ? (
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={[styles.scroll, { paddingBottom: bottomPadding }, scrollContentStyle]}
          refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={theme.colors.primary} /> : undefined}
        >
          {content}
        </ScrollView>
      ) : (
        content
      )}
    </SafeAreaView>
  );
}

function isStandalonePwaWeb() {
  if (Platform.OS !== 'web' || typeof window === 'undefined') {
    return false;
  }
  const matchStandalone = window.matchMedia?.('(display-mode: standalone)')?.matches;
  const navigatorStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone === true;
  return Boolean(matchStandalone || navigatorStandalone);
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
