import { useEffect, useRef } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { SectionCard } from '../ui/section-card';

type AutolearnLogPanelProps = {
  log?: string[];
  title?: string;
  subtitle?: string;
  compact?: boolean;
};

export function AutolearnLogPanel({
  log,
  title = 'Journal auto-learn',
  subtitle = "Flux runtime de l'auto-learner, avec les derniers evenements visibles en bas.",
  compact = false,
}: AutolearnLogPanelProps) {
  const logScrollRef = useRef<ScrollView | null>(null);
  const entries = log ?? [];

  useEffect(() => {
    logScrollRef.current?.scrollToEnd({ animated: false });
  }, [entries]);

  const body = (
    <View style={[styles.logFrame, compact ? styles.logFrameCompact : null]}>
      <ScrollView
        ref={logScrollRef}
        style={styles.logScroll}
        contentContainerStyle={styles.logContent}
        nestedScrollEnabled
        showsVerticalScrollIndicator={false}
        onContentSizeChange={() => {
          logScrollRef.current?.scrollToEnd({ animated: false });
        }}
      >
        {entries.length ? (
          entries.map((entry, index) => (
            <Text key={`${index}-${entry}`} style={styles.logEntry}>
              {entry}
            </Text>
          ))
        ) : (
          <Text style={styles.logEmpty}>Aucun evenement auto-learn a afficher.</Text>
        )}
      </ScrollView>
    </View>
  );

  if (compact) {
    return body;
  }

  return (
    <SectionCard title={title} subtitle={subtitle}>
      {body}
    </SectionCard>
  );
}

const styles = StyleSheet.create({
  logFrame: {
    minHeight: 220,
    maxHeight: 260,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#d9cfbe',
    backgroundColor: '#201812',
    overflow: 'hidden',
  },
  logFrameCompact: {
    minHeight: 180,
    maxHeight: 220,
  },
  logScroll: {
    flex: 1,
  },
  logContent: {
    flexGrow: 1,
    justifyContent: 'flex-end',
    paddingHorizontal: 14,
    paddingVertical: 14,
    gap: 8,
  },
  logEntry: {
    color: '#ece3d5',
    fontSize: 13,
    lineHeight: 19,
    fontFamily: 'Menlo',
  },
  logEmpty: {
    color: '#b8aa95',
    fontSize: 13,
    lineHeight: 19,
    fontStyle: 'italic',
  },
});