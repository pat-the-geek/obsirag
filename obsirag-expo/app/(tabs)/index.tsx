import { useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';

import { AutolearnLogPanel } from '../../components/system/autolearn-log-panel';
import { SystemStartupView } from '../../components/system/system-startup-view';
import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { StatusPill } from '../../components/ui/status-pill';
import { useServerConfig } from '../../features/auth/use-server-config';
import { useNoteSearch } from '../../features/notes/use-notes';
import { useSystemStatus } from '../../features/system/use-system-status';
import { useAppTheme } from '../../theme/app-theme';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';
import { buildNoteRoute } from '../../utils/note-route';

const appIcon = require('../../assets/app-icon.png');
const appPackage = require('../../package.json') as {
  dependencies?: Record<string, string>;
};

type HeroBadgeTone = 'frontend' | 'ai' | 'backend' | 'runtime';

type HeroBadge = {
  icon: string;
  label: string;
  tone: HeroBadgeTone;
};

export default function DashboardScreen() {
  const router = useRouter();
  const theme = useAppTheme();
  const [noteQuery, setNoteQuery] = useState('');
  const { backendUrl, useMockServer } = useServerConfig();
  const { data, isLoading, isRefetching, refetch, isError, error } = useSystemStatus({ refetchIntervalMs: 1200 });
  const noteSearch = useNoteSearch(noteQuery);

  if (isLoading || !data) {
    return (
      <Screen>
        <ActivityIndicator />
      </Screen>
    );
  }

  if (isError) {
    return (
      <Screen backgroundColor={theme.colors.background} refreshing={isRefetching} onRefresh={refetch}>
        <SystemStartupView
          startup={{
            ready: false,
            steps: ['Connexion au backend', 'Lecture de l’état du système'],
            currentStep: 'Impossible de récupérer le statut du système',
            error: error instanceof Error ? error.message : 'Erreur inconnue',
          }}
          loading={false}
          onContinue={() => refetch()}
          continueLabel="Réessayer"
        />
      </Screen>
    );
  }

  if (!data.startup?.ready) {
    return (
      <Screen backgroundColor={theme.colors.background} refreshing={isRefetching} onRefresh={refetch}>
        <SystemStartupView
          {...(data.startup ? { startup: data.startup } : {})}
          backendReachable={data.backendReachable}
          llmAvailable={data.llmAvailable}
          notesIndexed={data.notesIndexed}
          chunksIndexed={data.chunksIndexed}
        />
        <AutolearnLogPanel {...(data.autolearn?.log ? { log: data.autolearn.log } : {})} compact />
      </Screen>
    );
  }

  const autolearnLog = data.autolearn?.log ?? [];
  const indexingStatus = formatIndexingStatus(data.indexing);
  const autolearnStatus = formatStatusValue(data.autolearn?.step, 'Inactif');
  const stackBadges = buildDashboardBadges(data);
  const activeLlmModel = formatActiveModelValue(data.runtime?.llmModel);
  const euriaProvider = formatEuriaProviderValue(data.runtime?.euriaProvider);
  const euriaModel = formatEuriaModelValue(data.runtime?.euriaModel);
  const euriaStatus = data.runtime?.euriaEnabled ? 'Disponible' : 'Non configure';
  const runtimeSourceLabel = useMockServer ? 'Donnees mock locales' : 'API FastAPI live';
  const connectionModeLabel = useMockServer ? 'Mode mock' : 'Mode live';

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      <View style={[styles.heroCard, { borderColor: theme.colors.border, backgroundColor: theme.colors.surface }]}>
        <Image source={appIcon} style={styles.heroImage} resizeMode="contain" />
        <View style={styles.heroCopy}>
          <Text style={[styles.heroEyebrow, { color: theme.colors.primary }]}>ObsiRAG</Text>
          <Text style={[styles.heroTitle, { color: theme.colors.text }]}>Dashboard</Text>
          <Text style={[styles.heroSubtitle, { color: theme.colors.textMuted }]}>Vue d’ensemble du runtime, des recherches rapides et de l’activité de l’auto-learner.</Text>
          <View style={styles.modelCardsRow}>
            <View style={[styles.activeModelCard, styles.heroInfoCard, { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted }] }>
              <Text style={[styles.activeModelLabel, { color: theme.colors.primary }]}>LLM actif ObsiRAG</Text>
              <Text selectable style={[styles.activeModelValue, { color: theme.colors.text }]}>{activeLlmModel}</Text>
              <Text style={[styles.activeModelMeta, { color: theme.colors.textMuted }]}>Source runtime: {runtimeSourceLabel}</Text>
              <Text selectable style={[styles.activeModelMeta, { color: theme.colors.textMuted }]}>Backend: {backendUrl}</Text>
            </View>
            <View style={[styles.activeModelCard, styles.heroInfoCard, { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted }] }>
              <Text style={[styles.activeModelLabel, { color: theme.colors.primary }]}>Euria Infomaniak</Text>
              <Text selectable style={[styles.activeModelValue, { color: theme.colors.text }]}>{euriaModel}</Text>
              <Text style={[styles.activeModelMeta, { color: theme.colors.textMuted }]}>Provider: {euriaProvider}</Text>
              <Text style={[styles.activeModelMeta, { color: theme.colors.textMuted }]}>Statut: {euriaStatus}</Text>
            </View>
          </View>
          <View style={styles.badgeRow}>
            {stackBadges.map((badge) => (
              <View key={`${badge.tone}-${badge.label}`} style={[styles.heroBadge, badge.tone === 'frontend' ? styles.heroBadgeFrontend : null, badge.tone === 'ai' ? styles.heroBadgeAi : null, badge.tone === 'backend' ? styles.heroBadgeBackend : null, badge.tone === 'runtime' ? styles.heroBadgeRuntime : null]}>
                <Text style={[styles.heroBadgeLabel, badge.tone === 'frontend' ? styles.heroBadgeLabelFrontend : null, badge.tone === 'ai' ? styles.heroBadgeLabelAi : null, badge.tone === 'backend' ? styles.heroBadgeLabelBackend : null, badge.tone === 'runtime' ? styles.heroBadgeLabelRuntime : null]}>{badge.icon} {badge.label}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>
      <SectionCard title="Etat du systeme" subtitle="Synthese rapide du runtime ObsiRAG expose par le backend.">
        <StatusPill label={data.backendReachable ? 'Backend joignable' : 'Backend indisponible'} tone={data.backendReachable ? 'success' : 'danger'} />
        <StatusPill label={connectionModeLabel} tone={useMockServer ? 'warning' : 'success'} />
        <Text style={{ color: theme.colors.text }}>Indexation: {indexingStatus}</Text>
        <Text style={{ color: theme.colors.text }}>Auto-learn: {autolearnStatus}</Text>
        <Text style={{ color: theme.colors.text }}>Source runtime: {runtimeSourceLabel}</Text>
        <SystemStartupView
          {...(data.startup ? { startup: data.startup } : {})}
          backendReachable={data.backendReachable}
          llmAvailable={data.llmAvailable}
          notesIndexed={data.notesIndexed}
          chunksIndexed={data.chunksIndexed}
          compact
        />
      </SectionCard>
      <SectionCard title="Acces rapides" subtitle="Recherche de note et navigation directe depuis le dashboard.">
        <TextInput
          value={noteQuery}
          onChangeText={setNoteQuery}
          placeholder="Rechercher une note"
          placeholderTextColor={theme.colors.textSubtle}
          style={[styles.input, { borderColor: theme.colors.border, backgroundColor: theme.colors.surface, color: theme.colors.text }]}
        />
        {(noteSearch.data ?? []).slice(0, 6).map((item) => (
          <Pressable key={item.filePath} style={[styles.quickResult, { borderColor: theme.colors.border, backgroundColor: theme.colors.surfaceMuted }]} onPress={() => router.push(buildNoteRoute(item.filePath))}>
            <Text style={[styles.quickTitle, { color: theme.colors.text }]}>{item.title}</Text>
            <Text style={[styles.quickMeta, { color: theme.colors.textMuted }]}>{item.filePath}</Text>
            {joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ]) ? (
              <Text style={[styles.quickMeta, { color: theme.colors.textSubtle }]}>
                {joinMetadataParts([
                  item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
                  formatSizeBytes(item.sizeBytes),
                ])}
              </Text>
            ) : null}
          </Pressable>
        ))}
      </SectionCard>
      <AutolearnLogPanel log={autolearnLog} />
    </Screen>
  );
}

function formatStatusValue(value: string | undefined, fallback: string) {
  const trimmed = value?.trim();
  return trimmed ? trimmed : fallback;
}

function formatIndexingStatus(indexing: NonNullable<ReturnType<typeof useSystemStatus>['data']>['indexing']) {
  if (!indexing?.running) {
    return 'Aucun traitement en cours';
  }
  return formatStatusValue(indexing.current, 'Indexation en cours');
}

function buildDashboardBadges(data: NonNullable<ReturnType<typeof useSystemStatus>['data']>): HeroBadge[] {
  const runtime = data.runtime;
  const llmName = formatModelName(runtime?.llmModel ?? 'LLM local');
  return [
    { icon: 'UI', label: `React ${formatReactBadgeVersion(appPackage.dependencies?.react)}`, tone: 'frontend' },
    { icon: 'EX', label: `Expo ${formatExpoBadgeVersion(appPackage.dependencies?.expo)}`, tone: 'frontend' },
    { icon: 'AI', label: `${runtime?.llmProvider ?? 'MLX'} local`, tone: 'ai' },
    { icon: 'LLM', label: llmName, tone: 'ai' },
    { icon: 'EMB', label: shortModelLabel(runtime?.embeddingModel, 'MiniLM'), tone: 'ai' },
    { icon: 'NER', label: shortModelLabel(runtime?.nerModel, 'xx_ent_wiki_sm'), tone: 'ai' },
    { icon: 'API', label: data.backendReachable ? 'FastAPI online' : 'FastAPI offline', tone: 'backend' },
    { icon: 'DB', label: formatVectorStoreLabel(runtime?.vectorStore), tone: 'backend' },
    { icon: 'RUN', label: data.autolearn?.managedBy === 'worker' || runtime?.autolearnMode === 'worker' ? 'Auto-learn worker' : 'Auto-learn intégré', tone: 'runtime' },
    { icon: 'OK', label: data.llmAvailable ? 'LLM prêt' : 'LLM en attente', tone: 'runtime' },
  ];
}

function formatModelName(model: string) {
  const trimmed = model.trim();
  if (!trimmed) {
    return 'LLM local';
  }
  const compact = trimmed.split('/').pop() ?? trimmed;
  return compact.replace(/-4bit$/i, ' 4bit');
}

function formatReactBadgeVersion(version: string | undefined) {
  const normalized = normalizeSemver(version);
  if (!normalized) {
    return 'React';
  }

  const [major = normalized, minor] = normalized.split('.');
  return minor ? `${major}.${minor}` : major;
}

function formatExpoBadgeVersion(version: string | undefined) {
  const normalized = normalizeSemver(version);
  if (!normalized) {
    return 'SDK';
  }

  return normalized.split('.')[0] ?? normalized;
}

function normalizeSemver(version: string | undefined) {
  const trimmed = version?.trim();
  if (!trimmed) {
    return '';
  }

  const match = trimmed.match(/(\d+\.\d+\.\d+|\d+\.\d+|\d+)/);
  return match?.[0] ?? '';
}

function formatVectorStoreLabel(value: string | undefined) {
  const trimmed = value?.trim();
  return trimmed || 'ChromaDB';
}

function shortModelLabel(model: string | undefined, fallback: string) {
  const trimmed = model?.trim();
  if (!trimmed) {
    return fallback;
  }
  return trimmed.split('/').pop() ?? trimmed;
}

function formatActiveModelValue(model: string | undefined) {
  const trimmed = model?.trim();
  if (!trimmed) {
    return 'Chargement du modèle MLX…';
  }
  return trimmed;
}

function formatEuriaProviderValue(provider: string | undefined) {
  const trimmed = provider?.trim();
  return trimmed || 'Infomaniak';
}

function formatEuriaModelValue(model: string | undefined) {
  const trimmed = model?.trim();
  return trimmed || 'Modele non expose';
}

const styles = StyleSheet.create({
  heroCard: {
    borderRadius: 28,
    borderWidth: 1,
    paddingHorizontal: 18,
    paddingVertical: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  heroImage: {
    width: 92,
    height: 92,
    borderRadius: 24,
  },
  heroCopy: {
    flex: 1,
    gap: 8,
  },
  heroEyebrow: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  heroTitle: {
    fontSize: 28,
    fontWeight: '800',
  },
  heroSubtitle: {
    fontSize: 14,
    lineHeight: 20,
  },
  activeModelCard: {
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 4,
  },
  modelCardsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  heroInfoCard: {
    flexGrow: 1,
    flexShrink: 1,
    minWidth: 240,
  },
  activeModelLabel: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  activeModelValue: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  activeModelMeta: {
    fontSize: 12,
    lineHeight: 18,
    fontWeight: '600',
  },
  badgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    paddingTop: 4,
  },
  heroBadge: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  heroBadgeFrontend: {
    backgroundColor: '#edf6ff',
    borderColor: '#bfd9ee',
  },
  heroBadgeAi: {
    backgroundColor: '#fff3df',
    borderColor: '#edcc96',
  },
  heroBadgeBackend: {
    backgroundColor: '#eef8ef',
    borderColor: '#c4dfc8',
  },
  heroBadgeRuntime: {
    backgroundColor: '#f6efe9',
    borderColor: '#dfcbbb',
  },
  heroBadgeLabel: {
    fontSize: 11,
    fontWeight: '700',
  },
  heroBadgeLabelFrontend: {
    color: '#23557d',
  },
  heroBadgeLabelAi: {
    color: '#8a4f0a',
  },
  heroBadgeLabelBackend: {
    color: '#2f6a39',
  },
  heroBadgeLabelRuntime: {
    color: '#6f4a2b',
  },
  input: {
    borderWidth: 1,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  quickResult: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 12,
    gap: 4,
  },
  quickTitle: {
    fontWeight: '700',
  },
  quickMeta: {
    fontSize: 12,
  },
});
