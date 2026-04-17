import { useDeferredValue, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQueryClient } from '@tanstack/react-query';

import { KnowledgeGraph } from '../../components/graph/knowledge-graph';
import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { TagPill } from '../../components/ui/tag-pill';
import { useServerConfig } from '../../features/auth/use-server-config';
import { useGraph, useGraphSubgraph } from '../../features/graph/use-graph';

const FILTER_OPTION_LIMIT = 15;
const MIN_GRAPH_ZOOM = 0.2;
const MAX_GRAPH_ZOOM = 10;

export default function GraphScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ tag?: string }>();
  const queryClient = useQueryClient();
  const { api, useMockServer, setUseMockServer } = useServerConfig();
  const initialTag = useMemo(() => {
    const rawValue = Array.isArray(params.tag) ? params.tag[0] : params.tag;
    return rawValue?.trim() || undefined;
  }, [params.tag]);
  const [focusedNodeId, setFocusedNodeId] = useState<string | undefined>(undefined);
  const [zoom, setZoom] = useState(1);
  const [selectedGroup, setSelectedGroup] = useState<string | undefined>(undefined);
  const [selectedTag, setSelectedTag] = useState<string | undefined>(initialTag);
  const [selectedType, setSelectedType] = useState<string | undefined>(undefined);
  const [openFilter, setOpenFilter] = useState<'group' | 'tag' | 'type' | 'date' | null>(null);
  const [searchText, setSearchText] = useState('');
  const [recencyDays, setRecencyDays] = useState<number | undefined>(undefined);
  const [noteSearchText, setNoteSearchText] = useState('');
  const deferredSearchText = useDeferredValue(searchText);
  const graphFilters = useMemo(() => ({
    ...(selectedGroup ? { folders: [selectedGroup] } : {}),
    ...(selectedTag ? { tags: [selectedTag] } : {}),
    ...(selectedType ? { noteTypes: [selectedType] } : {}),
    ...(deferredSearchText.trim() ? { searchText: deferredSearchText.trim() } : {}),
    ...(recencyDays ? { recencyDays } : {}),
  }), [deferredSearchText, recencyDays, selectedGroup, selectedTag, selectedType]);
  const { data, isLoading, isRefetching, refetch } = useGraph(graphFilters);
  const subgraph = useGraphSubgraph(focusedNodeId, 1, graphFilters);
  const graphData = focusedNodeId ? subgraph.data : data;
  const graphLoading = focusedNodeId ? subgraph.isLoading : isLoading;
  const graphRefreshing = focusedNodeId ? subgraph.isRefetching : isRefetching;
  const availableGroups = useMemo(() => rankOptionsByUsage(
    graphData?.filterOptions.folders ?? [],
    graphData?.nodes.flatMap((node) => node.group ? [node.group] : []) ?? [],
  ), [graphData?.filterOptions.folders, graphData?.nodes]);
  const availableTags = useMemo(() => rankOptionsByUsage(
    graphData?.filterOptions.tags ?? [],
    graphData?.nodes.flatMap((node) => node.tags ?? []) ?? [],
  ), [graphData?.filterOptions.tags, graphData?.nodes]);
  const availableTypes = graphData?.filterOptions.types ?? [];
  const recencyOptions = useMemo(() => ([
    { label: 'Toutes les dates', value: undefined },
    { label: '7 jours', value: 7 },
    { label: '30 jours', value: 30 },
    { label: '90 jours', value: 90 },
  ]), []);
  const visibleNoteOptions = useMemo(() => {
    const search = noteSearchText.trim().toLowerCase();
    const options = graphData?.noteOptions ?? [];
    if (!search) {
      return options.slice(0, 8);
    }
    return options
      .filter((note) => note.title.toLowerCase().includes(search) || note.filePath.toLowerCase().includes(search))
      .slice(0, 8);
  }, [graphData?.noteOptions, noteSearchText]);

  const switchToLiveBackend = async () => {
    setUseMockServer(false);
    await queryClient.invalidateQueries();
  };

  const detectSynapsesForNode = async (nodeId: string) => {
    try {
      const result = await api.detectNoteSynapses(nodeId);
      await queryClient.invalidateQueries();

      const firstCreated = result.created[0];
      if (firstCreated) {
        Alert.alert('Synapses detectees', result.message, [
          { text: 'Fermer', style: 'cancel' },
          { text: 'Ouvrir la premiere', onPress: () => router.push(`/(tabs)/note/${encodeURIComponent(firstCreated.filePath)}`) },
        ]);
        return;
      }

      Alert.alert('Detection terminee', result.message);
    } catch (error) {
      Alert.alert('Detection impossible', error instanceof Error ? error.message : 'Erreur inconnue');
    }
  };

  const headerFilters = graphData ? (
    <View style={styles.headerFiltersRow}>
      <FilterDropdown
        label={selectedGroup ?? 'Tous les groupes'}
        size="wide"
        isOpen={openFilter === 'group'}
        onToggle={() => setOpenFilter((value) => value === 'group' ? null : 'group')}
        options={[
          { label: 'Tous les groupes', onSelect: () => setSelectedGroup(undefined) },
          ...availableGroups.map((group) => ({ label: `${group.label} · ${group.count}`, onSelect: () => setSelectedGroup(group.value) })),
        ]}
        onClose={() => setOpenFilter(null)}
      />
      <FilterDropdown
        label={selectedTag ? `#${selectedTag}` : 'Tous les tags'}
        size="wide"
        isOpen={openFilter === 'tag'}
        onToggle={() => setOpenFilter((value) => value === 'tag' ? null : 'tag')}
        options={[
          { label: 'Tous les tags', onSelect: () => setSelectedTag(undefined) },
          ...availableTags.map((tag) => ({ label: `#${tag.label} · ${tag.count}`, onSelect: () => setSelectedTag(tag.value) })),
        ]}
        onClose={() => setOpenFilter(null)}
      />
      <FilterDropdown
        label={selectedType ? labelForType(selectedType) : 'Tous les types'}
        size="compact"
        isOpen={openFilter === 'type'}
        onToggle={() => setOpenFilter((value) => value === 'type' ? null : 'type')}
        options={[
          { label: 'Tous les types', onSelect: () => setSelectedType(undefined) },
          ...availableTypes.map((noteType) => ({ label: labelForType(noteType), onSelect: () => setSelectedType(noteType) })),
        ]}
        onClose={() => setOpenFilter(null)}
      />
      <FilterDropdown
        label={recencyOptions.find((option) => option.value === recencyDays)?.label ?? 'Toutes les dates'}
        size="compact"
        isOpen={openFilter === 'date'}
        onToggle={() => setOpenFilter((value) => value === 'date' ? null : 'date')}
        options={recencyOptions.map((option) => ({ label: option.label, onSelect: () => setRecencyDays(option.value) }))}
        onClose={() => setOpenFilter(null)}
      />
    </View>
  ) : null;

  return (
    <Screen refreshing={graphRefreshing} onRefresh={focusedNodeId ? subgraph.refetch : refetch} scrollContentStyle={{ paddingBottom: 24 + insets.bottom }}>
      <SectionCard title="Graphe de connaissances" headerAccessory={headerFilters}>
        {graphLoading || !graphData ? <ActivityIndicator /> : null}
        {graphData ? (
          <>
            <KnowledgeGraph
              data={graphData}
              {...(focusedNodeId ? { focusedNodeId } : {})}
              onSelectNode={setFocusedNodeId}
              onOpenNode={(nodeId) => router.push(`/(tabs)/note/${encodeURIComponent(nodeId)}`)}
              onDetectSynapses={(nodeId) => { void detectSynapsesForNode(nodeId); }}
              onZoomChange={(value) => setZoom(Number(clamp(value, MIN_GRAPH_ZOOM, MAX_GRAPH_ZOOM).toFixed(2)))}
              zoom={zoom}
              onZoomOut={() => setZoom((value) => Math.max(MIN_GRAPH_ZOOM, Number((value - 0.2).toFixed(2))))}
              onZoomIn={() => setZoom((value) => Math.min(MAX_GRAPH_ZOOM, Number((value + 0.2).toFixed(2))))}
              onZoomReset={() => setZoom(1)}
            />
            {focusedNodeId ? (
              <Pressable style={styles.resetButton} onPress={() => setFocusedNodeId(undefined)}>
                <Text style={styles.resetButtonText}>Revenir a la vue d'ensemble</Text>
              </Pressable>
            ) : null}
            {useMockServer ? (
              <View style={styles.mockBanner}>
                <Text style={styles.warningText}>Le graphe affiche actuellement les donnees mock de demonstration, limitees a 3 noeuds.</Text>
                <Pressable style={styles.liveButton} onPress={() => { void switchToLiveBackend(); }}>
                  <Text style={styles.liveButtonText}>Basculer en live</Text>
                </Pressable>
              </View>
            ) : null}
            {selectedTag ? (
              <View style={styles.activeTagRow}>
                <TagPill label={selectedTag} onPress={() => setSelectedTag(undefined)} />
                <Text style={styles.helperText}>Filtre actif. Touchez le tag pour le retirer.</Text>
              </View>
            ) : null}
            <Text>{graphData.metrics.nodeCount} noeuds · {graphData.metrics.edgeCount} aretes · densite {graphData.metrics.density}</Text>
            <Text style={styles.helperText}>{graphData.metrics.filteredNoteCount ?? graphData.metrics.nodeCount} / {graphData.metrics.totalNoteCount ?? graphData.metrics.nodeCount} notes affichees</Text>
            <TextInput
              value={searchText}
              onChangeText={setSearchText}
              placeholder="Recherche titre, chemin ou tag"
              placeholderTextColor="#8a7760"
              style={styles.searchInput}
            />
            <View style={styles.legendRow}>
              {graphData.legend.map((item) => (
                <View key={item.key} style={styles.legendItem}>
                  <View style={[styles.legendDot, { backgroundColor: item.color }]} />
                  <Text style={styles.legendText}>{item.label}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.helperText}>Touchez un noeud pour isoler son voisinage direct, recentrer la camera et explorer le sous-graphe correspondant. Un double-clic ouvre directement la note.</Text>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Ouvrir une note</Text>
              <TextInput
                value={noteSearchText}
                onChangeText={setNoteSearchText}
                placeholder="Recherche alphabetique d'une note"
                placeholderTextColor="#8a7760"
                style={styles.searchInput}
              />
              {visibleNoteOptions.length ? visibleNoteOptions.map((note) => (
                <Pressable key={`note-option-${note.filePath}`} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(note.filePath)}`)} style={styles.summaryRow}>
                  <Text style={styles.summaryRowTitle}>{note.title}</Text>
                  <Text style={styles.summaryRowMeta}>{labelForType(note.noteType ?? 'user')} · {shortPath(note.filePath)}</Text>
                </Pressable>
              )) : <Text style={styles.summaryEmpty}>Aucune note ne correspond a cette recherche.</Text>}
            </View>
            <View style={styles.summaryGrid}>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryTitle}>Parcours par centralite</Text>
                {graphData.spotlight.length ? graphData.spotlight.map((node) => (
                  <Pressable key={`spotlight-${node.filePath}`} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(node.filePath)}`)} style={styles.summaryRow}>
                    <Text style={styles.summaryRowTitle}>{node.title}</Text>
                    <Text style={styles.summaryRowMeta}>centralite {node.score}{node.dateModified ? ` · ${formatDate(node.dateModified)}` : ''}</Text>
                  </Pressable>
                )) : <Text style={styles.summaryEmpty}>Aucun noeud central avec ces filtres.</Text>}
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryTitle}>Parcours recent</Text>
                {graphData.recentNotes.length ? graphData.recentNotes.map((node) => (
                  <Pressable key={`recent-${node.filePath}`} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(node.filePath)}`)} style={styles.summaryRow}>
                    <Text style={styles.summaryRowTitle}>{node.title}</Text>
                    <Text style={styles.summaryRowMeta}>{node.dateModified ? formatDate(node.dateModified) : 'date inconnue'}</Text>
                  </Pressable>
                )) : <Text style={styles.summaryEmpty}>Aucune note recente avec ces filtres.</Text>}
              </View>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>Repartition des filtres</Text>
              <View style={styles.breakdownGrid}>
                <View style={styles.breakdownColumn}>
                  <Text style={styles.breakdownTitle}>Dossiers dominants</Text>
                  {graphData.folderSummary.length ? graphData.folderSummary.map((item) => <Text key={`folder-${item.label}`} style={styles.breakdownText}>{item.label} · {item.count}</Text>) : <Text style={styles.summaryEmpty}>Aucun dossier.</Text>}
                </View>
                <View style={styles.breakdownColumn}>
                  <Text style={styles.breakdownTitle}>Tags dominants</Text>
                  {graphData.tagSummary.length ? (
                    <View style={styles.tagSummaryList}>
                      {graphData.tagSummary.map((item) => (
                        <View key={`tag-${item.label}`} style={styles.tagSummaryItem}>
                          <TagPill label={item.label} onPress={() => setSelectedTag(item.label)} />
                          <Text style={styles.breakdownText}>{item.count}</Text>
                        </View>
                      ))}
                    </View>
                  ) : <Text style={styles.summaryEmpty}>Aucun tag.</Text>}
                </View>
                <View style={styles.breakdownColumn}>
                  <Text style={styles.breakdownTitle}>Types visibles</Text>
                  {graphData.typeSummary.length ? graphData.typeSummary.map((item) => <Text key={`type-${item.label}`} style={styles.breakdownText}>{labelForType(item.label)} · {item.count}</Text>) : <Text style={styles.summaryEmpty}>Aucun type.</Text>}
                </View>
              </View>
            </View>
            {graphData.topNodes.map((node) => (
              <View key={node.id} style={styles.nodeCard}>
                <Text style={styles.nodeTitle}>{node.label}</Text>
                <Text style={styles.nodeMeta}>Degre {node.degree}</Text>
                <View style={styles.nodeActions}>
                  <Pressable onPress={() => setFocusedNodeId(node.id)} style={styles.focusButton}>
                    <Text style={styles.focusButtonText}>Focus</Text>
                  </Pressable>
                  <Pressable onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(node.id)}`)} style={styles.openButton}>
                    <Text style={styles.openButtonText}>Ouvrir</Text>
                  </Pressable>
                </View>
              </View>
            ))}
          </>
        ) : null}
      </SectionCard>
    </Screen>
  );
}

function rankOptionsByUsage(allOptions: string[], usedOptions: string[]) {
  const usage = new Map<string, number>();

  usedOptions.forEach((option) => {
    usage.set(option, (usage.get(option) ?? 0) + 1);
  });

  return allOptions
    .slice()
    .sort((left, right) => {
      const usageDelta = (usage.get(right) ?? 0) - (usage.get(left) ?? 0);
      if (usageDelta !== 0) {
        return usageDelta;
      }
      return left.localeCompare(right, 'fr');
    })
    .map((option) => ({
      value: option,
      label: option,
      count: usage.get(option) ?? 0,
    }))
    .slice(0, FILTER_OPTION_LIMIT);
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

type FilterDropdownProps = {
  label: string;
  size?: 'compact' | 'wide';
  isOpen: boolean;
  onToggle: () => void;
  onClose: () => void;
  options: Array<{
    label: string;
    onSelect: () => void;
  }>;
};

function FilterDropdown({ label, size = 'wide', isOpen, onToggle, onClose, options }: FilterDropdownProps) {
  return (
    <View style={[styles.dropdownWrapper, size === 'compact' ? styles.dropdownWrapperCompact : styles.dropdownWrapperWide, isOpen && styles.dropdownWrapperOpen]}>
      <Pressable style={[styles.dropdownTrigger, isOpen && styles.dropdownTriggerOpen]} onPress={onToggle}>
        <Text style={[styles.dropdownTriggerText, size === 'compact' ? styles.dropdownTriggerTextCompact : styles.dropdownTriggerTextWide, isOpen && styles.dropdownTriggerTextOpen]} numberOfLines={1}>{label}</Text>
        <Text style={[styles.dropdownChevron, isOpen && styles.dropdownTriggerTextOpen]}>▾</Text>
      </Pressable>
      {isOpen ? (
        <View style={[styles.dropdownMenu, size === 'compact' ? styles.dropdownMenuCompact : styles.dropdownMenuWide]}>
          {options.map((option) => (
            <Pressable
              key={option.label}
              style={styles.dropdownOption}
              onPress={() => {
                option.onSelect();
                onClose();
              }}
            >
              <Text style={styles.dropdownOptionText}>{option.label}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  headerFiltersRow: {
    position: 'relative',
    zIndex: 40,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
    gap: 8,
  },
  dropdownWrapper: {
    position: 'relative',
    zIndex: 40,
  },
  dropdownWrapperWide: {
    minWidth: 196,
  },
  dropdownWrapperCompact: {
    minWidth: 150,
  },
  dropdownWrapperOpen: {
    zIndex: 80,
  },
  dropdownTrigger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  dropdownTriggerOpen: {
    backgroundColor: '#263e5f',
    borderColor: '#263e5f',
  },
  dropdownTriggerText: {
    color: '#3d2e20',
    fontWeight: '600',
    fontSize: 13,
  },
  dropdownTriggerTextWide: {
    maxWidth: 224,
  },
  dropdownTriggerTextCompact: {
    maxWidth: 140,
  },
  dropdownTriggerTextOpen: {
    color: '#f9f6f0',
  },
  dropdownChevron: {
    color: '#6f5d49',
    fontSize: 12,
  },
  dropdownMenu: {
    position: 'absolute',
    top: 42,
    left: 0,
    zIndex: 120,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#fffdfa',
    paddingVertical: 6,
    shadowColor: '#47331a',
    shadowOpacity: 0.12,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 6 },
    elevation: 12,
  },
  dropdownMenuWide: {
    minWidth: 240,
  },
  dropdownMenuCompact: {
    minWidth: 168,
  },
  dropdownOption: {
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  dropdownOptionText: {
    color: '#3d2e20',
    fontWeight: '600',
    fontSize: 13,
    flexShrink: 0,
  },
  mockBanner: {
    gap: 10,
  },
  warningText: {
    color: '#9f4f2d',
    lineHeight: 20,
    fontWeight: '600',
  },
  liveButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#263e5f',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  liveButtonText: {
    color: '#f9f6f0',
    fontWeight: '700',
  },
  activeTagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 10,
  },
  nodeCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#f8f3eb',
    padding: 12,
    gap: 4,
  },
  nodeTitle: {
    color: '#1f160c',
    fontWeight: '700',
  },
  nodeMeta: {
    color: '#6f5d49',
  },
  nodeActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  focusButton: {
    borderRadius: 999,
    backgroundColor: '#263e5f',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  focusButtonText: {
    color: '#f9f6f0',
    fontWeight: '700',
  },
  openButton: {
    borderRadius: 999,
    backgroundColor: '#e8ddd0',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  openButtonText: {
    color: '#3d2e20',
    fontWeight: '700',
  },
  resetButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#e8ddd0',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  resetButtonText: {
    color: '#3d2e20',
    fontWeight: '700',
  },
  helperText: {
    color: '#6f5d49',
    lineHeight: 20,
  },
  searchInput: {
    borderWidth: 1,
    borderColor: '#d8cfc0',
    borderRadius: 14,
    backgroundColor: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#1f160c',
  },
  legendRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginTop: 4,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  legendText: {
    color: '#6f5d49',
    fontSize: 12,
    fontWeight: '600',
  },
  summaryGrid: {
    gap: 12,
  },
  summaryCard: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#d8cfc0',
    backgroundColor: '#fffdfa',
    padding: 12,
    gap: 8,
  },
  summaryTitle: {
    color: '#1f160c',
    fontWeight: '700',
  },
  summaryRow: {
    gap: 2,
  },
  summaryRowTitle: {
    color: '#1f160c',
    fontWeight: '600',
  },
  summaryRowMeta: {
    color: '#6f5d49',
    fontSize: 12,
  },
  summaryEmpty: {
    color: '#6f5d49',
    fontSize: 12,
  },
  breakdownGrid: {
    gap: 10,
  },
  breakdownColumn: {
    gap: 6,
  },
  tagSummaryList: {
    gap: 8,
  },
  tagSummaryItem: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 8,
  },
  breakdownTitle: {
    color: '#3d2e20',
    fontWeight: '700',
  },
  breakdownText: {
    color: '#6f5d49',
    fontSize: 12,
  },
});

function parseDate(value?: string) {
  if (!value) {
    return undefined;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

function formatDate(value?: string) {
  const parsed = parseDate(value);
  if (!parsed) {
    return 'date inconnue';
  }
  return parsed.toISOString().slice(0, 10);
}

function labelForType(noteType: string) {
  switch (noteType) {
    case 'user':
      return 'Note';
    case 'report':
      return 'Rapport';
    case 'insight':
      return 'Insight';
    case 'synapse':
      return 'Synapse';
    default:
      return noteType;
  }
}

function shortPath(value: string) {
  const parts = value.split('/');
  return parts.length <= 2 ? value : parts.slice(-2).join('/');
}
