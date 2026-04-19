import { PropsWithChildren, RefObject } from 'react';
import { RefreshControl, ScrollView, StyleProp, StyleSheet, View, ViewStyle } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';

type ScreenProps = PropsWithChildren<{
  scroll?: boolean;
  refreshing?: boolean;
  onRefresh?: () => void;
  backgroundColor?: string;
  contentStyle?: StyleProp<ViewStyle>;
  scrollContentStyle?: StyleProp<ViewStyle>;
  scrollRef?: RefObject<ScrollView | null>;
}>;

export function Screen({ children, scroll = true, refreshing = false, onRefresh, backgroundColor, contentStyle, scrollContentStyle, scrollRef }: ScreenProps) {
  const insets = useSafeAreaInsets();
  const content = <View style={[styles.content, contentStyle]}>{children}</View>;

  return (
    <SafeAreaView edges={['top', 'right', 'bottom', 'left']} style={[styles.safeArea, backgroundColor ? { backgroundColor } : null]}>
      {scroll ? (
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={[styles.scroll, { paddingBottom: 20 + insets.bottom }, scrollContentStyle]}
          refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} /> : undefined}
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
    backgroundColor: '#f4f1ea',
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
