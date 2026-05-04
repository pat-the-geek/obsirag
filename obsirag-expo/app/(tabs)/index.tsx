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
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../utils/format-display';

const appIcon = require('../../assets/app-icon.png');

type HeroBadgeTone = 'frontend' | 'ai' | 'backend' | 'runtime';

type HeroBadge = {
  icon: string;
  label: string;
  tone: HeroBadgeTone;
};

export default function DashboardScreen() {
  const router = useRouter();
  const [noteQuery, setNoteQuery] = useState('');
  const [heroImageFailed, setHeroImageFailed] = useState(false);
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
      <Screen backgroundColor="#f4f1ea" refreshing={isRefetching} onRefresh={refetch}>
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
      <Screen backgroundColor="#f4f1ea" refreshing={isRefetching} onRefresh={refetch}>
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
  const euriaLlmModel = formatEuriaModelValue(data.runtime?.euriaModel);
  const runtimeSourceLabel = useMockServer ? 'Donnees mock locales' : 'API FastAPI live';
  const connectionModeLabel = useMockServer ? 'Mode mock' : 'Mode live';

  return (
    <Screen refreshing={isRefetching} onRefresh={refetch}>
      <View style={styles.heroCard}>
        {!heroImageFailed ? (
          <Image source={appIcon} style={styles.heroImage} resizeMode="contain" onError={() => setHeroImageFailed(true)} />
        ) : (
          <View style={styles.heroImageFallback}>
            <Text style={styles.heroImageFallbackText}>OR</Text>
          </View>
        )}
        <View style={styles.heroCopy}>
          <Text style={styles.heroEyebrow}>ObsiRAG</Text>
          <Text style={styles.heroTitle}>Dashboard</Text>
          <Text style={styles.heroSubtitle}>Vue d’ensemble du runtime, des recherches rapides et de l’activité de l’auto-learner.</Text>
          <View style={styles.activeModelCard}>
            <Text style={styles.activeModelLabel}>LLM actif ObsiRAG</Text>
            <Text selectable style={styles.activeModelValue}>LLM Local: {activeLlmModel}</Text>
            <Text selectable style={styles.activeModelValue}>LLM Euria: {euriaLlmModel}</Text>
            <Text style={styles.activeModelMeta}>Source runtime: {runtimeSourceLabel}</Text>
            <Text selectable style={styles.activeModelMeta}>Backend: {backendUrl}</Text>
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
        <Text>Indexation: {indexingStatus}</Text>
        <Text>Auto-learn: {autolearnStatus}</Text>
        <Text>Source runtime: {runtimeSourceLabel}</Text>
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
          placeholderTextColor="#8a7760"
          style={styles.input}
        />
        {(noteSearch.data ?? []).slice(0, 6).map((item) => (
          <Pressable key={item.filePath} style={styles.quickResult} onPress={() => router.push(`/(tabs)/note/${encodeURIComponent(item.filePath)}`)}>
            <Text style={styles.quickTitle}>{item.title}</Text>
            <Text style={styles.quickMeta}>{item.filePath}</Text>
            {joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ]) ? <Text style={styles.quickMeta}>{joinMetadataParts([
              item.dateModified ? `Modifie le ${formatMetadataDate(item.dateModified)}` : null,
              formatSizeBytes(item.sizeBytes),
            ])}</Text> : null}
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
    { icon: 'UI', label: 'React 19.1', tone: 'frontend' },
    { icon: 'EX', label: 'Expo 54', tone: 'frontend' },
    { icon: 'AI', label: `${runtime?.llmProvider ?? 'Ollama'} local`, tone: 'ai' },
    { icon: 'LLM', label: llmName, tone: 'ai' },
    { icon: 'EMB', label: shortModelLabel(runtime?.embeddingModel, 'MiniLM'), tone: 'ai' },
    { icon: 'NER', label: shortModelLabel(runtime?.nerModel, 'xx_ent_wiki_sm'), tone: 'ai' },
    { icon: 'API', label: data.backendReachable ? 'FastAPI online' : 'FastAPI offline', tone: 'backend' },
    { icon: 'DB', label: runtime?.vectorStore ?? 'LanceDB', tone: 'backend' },
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
    return 'Chargement du modèle Ollama…';
  }
  return trimmed;
}

function formatEuriaModelValue(model: string | undefined) {
  const trimmed = model?.trim();
  return trimmed || 'openai/gpt-oss-120b';
}

const styles = StyleSheet.create({
  heroCard: {
    borderRadius: 28,
    borderWidth: 1,
    borderColor: '#decdb8',
    backgroundColor: '#fbf5ea',
    paddingHorizontal: 18,
    paddingVertical: 20,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 16,
  },
  heroImage: {
    width: 92,
    height: 92,
    borderRadius: 24,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: '#decdb8',
    backgroundColor: '#fffaf2',
  },
  heroImageFallback: {
    width: 92,
    height: 92,
    borderRadius: 24,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: '#decdb8',
    backgroundColor: '#fffaf2',
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroImageFallbackText: {
    color: '#8a562b',
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  heroCopy: {
    flex: 1,
    gap: 8,
  },
  heroEyebrow: {
    color: '#8a562b',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.9,
    textTransform: 'uppercase',
  },
  heroTitle: {
    color: '#1f160c',
    fontSize: 28,
    fontWeight: '800',
  },
  heroSubtitle: {
    color: '#6f5d49',
    fontSize: 14,
    lineHeight: 20,
  },
  activeModelCard: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#e4cfb1',
    backgroundColor: '#fffaf2',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 4,
  },
  activeModelLabel: {
    color: '#8a562b',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  activeModelValue: {
    color: '#1f160c',
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '700',
  },
  activeModelMeta: {
    color: '#6f5d49',
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
    borderColor: '#d8cfc0',
    borderRadius: 14,
    backgroundColor: '#ffffff',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: '#1f160c',
  },
  quickResult: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#e0d5c7',
    backgroundColor: '#f8f3eb',
    padding: 12,
    gap: 4,
  },
  quickTitle: {
    color: '#1f160c',
    fontWeight: '700',
  },
  quickMeta: {
    color: '#6f5d49',
    fontSize: 12,
  },
});
