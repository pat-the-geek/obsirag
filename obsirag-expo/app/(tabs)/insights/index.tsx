import { startTransition, useDeferredValue, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, NativeScrollEvent, NativeSyntheticEvent, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { InsightListItem } from '../../../components/insights/insight-list-item';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useInsights } from '../../../features/insights/use-insights';

const INITIAL_INSIGHT_BATCH = 12;
const INITIAL_INSIGHT_WARMUP_BATCH = 12;
const INSIGHT_BATCH_STEP = 18;
const SCROLL_LOAD_THRESHOLD = 240;
const INITIAL_WARMUP_DELAY_MS = 140;

export default function InsightsScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState<'all' | 'insight' | 'synapse' | 'synthesis' | 'conversation'>('all');
  const [visibleCount, setVisibleCount] = useState(INITIAL_INSIGHT_BATCH);
  const { data, isLoading, isRefetching, refetch } = useInsights();
  const deferredSearch = useDeferredValue(search);

  const filtered = useMemo(() => {
    const searchValue = deferredSearch.trim().toLowerCase();
    return (data ?? []).filter((item) => {
      const matchesKind = kindFilter === 'all' || item.kind === kindFilter;
      const haystack = `${item.title} ${item.filePath} ${(item.tags ?? []).join(' ')}`.toLowerCase();
      const matchesSearch = !searchValue || haystack.includes(searchValue);
      return matchesKind && matchesSearch;
    });
  }, [data, deferredSearch, kindFilter]);

  useEffect(() => {
    setVisibleCount(INITIAL_INSIGHT_BATCH);
  }, [deferredSearch, kindFilter, data?.length]);

  useEffect(() => {
    if (filtered.length <= INITIAL_INSIGHT_BATCH || visibleCount !== INITIAL_INSIGHT_BATCH) {
      return;
    }

    const warmupTimer = setTimeout(() => {
      startTransition(() => {
        setVisibleCount((current) => Math.min(current + INITIAL_INSIGHT_WARMUP_BATCH, filtered.length));
      });
    }, INITIAL_WARMUP_DELAY_MS);

    return () => clearTimeout(warmupTimer);
  }, [filtered.length, visibleCount]);

  const visibleInsights = useMemo(() => filtered.slice(0, visibleCount), [filtered, visibleCount]);
  const canLoadMore = visibleInsights.length < filtered.length;

  const loadMoreInsights = () => {
    if (!canLoadMore) {
      return;
    }

    startTransition(() => {
      setVisibleCount((current) => Math.min(current + INSIGHT_BATCH_STEP, filtered.length));
    });
  };

  const handleScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    if (!canLoadMore) {
      return;
    }

    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const distanceToBottom = contentSize.height - (contentOffset.y + layoutMeasurement.height);
    if (distanceToBottom <= SCROLL_LOAD_THRESHOLD) {
      loadMoreInsights();
    }
  };

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch} onScroll={handleScroll}>
      <SectionCard title="Insights et artefacts" subtitle="Insights, synapses, syntheses et conversations sauvegardees.">
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Rechercher un artefact"
          placeholderTextColor="#8a7760"
          style={styles.input}
        />
        <View style={styles.filterRow}>
          {(['all', 'insight', 'synapse', 'synthesis', 'conversation'] as const).map((kind) => (
            <Pressable key={kind} style={[styles.filterChip, kindFilter === kind && styles.filterChipActive]} onPress={() => startTransition(() => setKindFilter(kind))}>
              <Text style={[styles.filterChipText, kindFilter === kind && styles.filterChipTextActive]}>{kind}</Text>
            </Pressable>
          ))}
        </View>
        {isLoading ? <ActivityIndicator /> : null}
        {!isLoading ? (
          <Text testID="insights-visible-count" style={styles.resultCount}>
            {visibleInsights.length} sur {filtered.length} élément{filtered.length > 1 ? 's' : ''}
          </Text>
        ) : null}
        {visibleInsights.map((item) => (
          <InsightListItem
            key={item.id}
            item={item}
            onPress={() => router.push(`/(tabs)/insights/${encodeURIComponent(item.id)}`)}
            onOpenTag={(tag) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(tag)}`)}
          />
        ))}
        {canLoadMore ? (
          <Pressable testID="insights-load-more" style={styles.loadMoreButton} onPress={loadMoreInsights}>
            <Text style={styles.loadMoreText}>Charger les éléments suivants</Text>
          </Pressable>
        ) : null}
      </SectionCard>
    </Screen>
  );
}

const styles = StyleSheet.create({
  input: {
    borderWidth: 1,
    borderColor: '#d8cfc0',
    borderRadius: 14,
    backgroundColor: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#1f160c',
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  filterChip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  filterChipActive: {
    backgroundColor: '#263e5f',
    borderColor: '#263e5f',
  },
  filterChipText: {
    color: '#5c4d3a',
    fontWeight: '600',
  },
  filterChipTextActive: {
    color: '#f9f6f0',
  },
  resultCount: {
    color: '#6b5b47',
    fontSize: 12,
    fontWeight: '600',
  },
  loadMoreButton: {
    alignSelf: 'center',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  loadMoreText: {
    color: '#3d2e20',
    fontWeight: '700',
  },
});
