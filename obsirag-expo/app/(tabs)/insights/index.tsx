import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { InsightListItem } from '../../../components/insights/insight-list-item';
import { Screen } from '../../../components/ui/screen';
import { SectionCard } from '../../../components/ui/section-card';
import { useInsights } from '../../../features/insights/use-insights';

export default function InsightsScreen() {
  const router = useRouter();
  const [search, setSearch] = useState('');
  const [kindFilter, setKindFilter] = useState<'all' | 'insight' | 'synapse' | 'synthesis' | 'conversation'>('all');
  const { data, isLoading, isRefetching, refetch } = useInsights();

  const filtered = useMemo(() => {
    const searchValue = search.trim().toLowerCase();
    return (data ?? []).filter((item) => {
      const matchesKind = kindFilter === 'all' || item.kind === kindFilter;
      const haystack = `${item.title} ${item.filePath} ${(item.tags ?? []).join(' ')}`.toLowerCase();
      const matchesSearch = !searchValue || haystack.includes(searchValue);
      return matchesKind && matchesSearch;
    });
  }, [data, kindFilter, search]);

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
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
            <Pressable key={kind} style={[styles.filterChip, kindFilter === kind && styles.filterChipActive]} onPress={() => setKindFilter(kind)}>
              <Text style={[styles.filterChipText, kindFilter === kind && styles.filterChipTextActive]}>{kind}</Text>
            </Pressable>
          ))}
        </View>
        {isLoading ? <ActivityIndicator /> : null}
        {filtered.map((item) => (
          <InsightListItem
            key={item.id}
            item={item}
            onPress={() => router.push(`/(tabs)/insights/${encodeURIComponent(item.id)}`)}
            onOpenTag={(tag) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(tag)}`)}
          />
        ))}
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
});
