import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';

import { LogConsole } from '../../components/ui/log-console';
import { Screen } from '../../components/ui/screen';
import { SectionCard } from '../../components/ui/section-card';
import { StatusPill } from '../../components/ui/status-pill';
import { useReindexData, useSystemLogs, useSystemStatus } from '../../features/system/use-system-status';
import { useAppStore } from '../../store/app-store';
import { formatFontSizeModeLabel, formatThemeModeLabel, scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';

export default function SettingsScreen() {
  const themeMode = useAppStore((state) => state.themeMode);
  const setThemeMode = useAppStore((state) => state.setThemeMode);
  const increaseFontSize = useAppStore((state) => state.increaseFontSize);
  const decreaseFontSize = useAppStore((state) => state.decreaseFontSize);
  const theme = useAppTheme();
  const fontScale = useAppFontScale();
  const { data, refetch, isRefetching } = useSystemStatus();
  const reindexData = useReindexData();
  const { data: logEntries = [] } = useSystemLogs();

  const autolearnLabel = data?.autolearn?.running
    ? data.autolearn.managedBy === 'worker'
      ? 'Worker separe actif'
      : 'Auto-learner actif'
    : data?.autolearn?.managedBy === 'worker'
      ? 'Worker separe inactif'
      : 'Auto-learner inactif';

  const autolearnTone = data?.autolearn?.running ? 'success' : 'neutral';
  const indexingTone = data?.indexing?.running ? 'warning' : 'success';
  const indexingLabel = data?.indexing?.running
    ? `Indexation en cours ${data.indexing.processed}/${data.indexing.total || '?'}`
    : 'Index ChromaDB pret';

  const onReindex = () => {
    reindexData.mutate(undefined, {
      onSuccess: (result) => {
        Alert.alert(
          'Reindexation terminee',
          `+${result.added} ajoutees, ${result.updated} mises a jour, ${result.deleted} supprimees, ${result.skipped} ignorees.`,
        );
      },
      onError: (error) => {
        Alert.alert('Reindexation impossible', error instanceof Error ? error.message : 'La reindexation a echoue.');
      },
    });
  };

  const themeOptions: Array<{ value: 'system' | 'light' | 'dark' | 'quiet' | 'abyss'; title: string; subtitle: string }> = [
    { value: 'system', title: 'Automatique', subtitle: `Suit le systeme (${theme.resolvedMode === 'dark' ? 'Dark+' : 'Light+'})` },
    { value: 'light', title: 'Light+', subtitle: 'Palette claire inspiree de VS Code' },
    { value: 'dark', title: 'Dark+', subtitle: 'Palette sombre inspiree de VS Code' },
    { value: 'quiet', title: 'Atelier', subtitle: 'Clair doux inspire de VS Code Quiet Light, plus editorial et pose' },
    { value: 'abyss', title: 'Noctis', subtitle: 'Bleu nuit profond inspire de VS Code Abyss, plus immersif et contraste' },
  ];

  return (
    <Screen refreshing={isRefetching || reindexData.isPending} onRefresh={() => { void refetch(); }}>
      <SectionCard title="Affichage" subtitle="Choisissez le rendu global de l'application Expo.">
        <StatusPill label={`Theme actif: ${themeMode === 'system' ? `${formatThemeModeLabel(themeMode)} (${theme.resolvedMode === 'dark' ? 'Dark+' : 'Light+'})` : formatThemeModeLabel(themeMode)}`} tone="neutral" />
        <View style={[styles.fontSizePanel, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }] }>
          <View style={styles.fontSizeCopy}>
            <Text style={[styles.themeOptionTitle, { color: theme.colors.text, fontSize: scaleFontSize(16, fontScale.scale) }]}>Taille du texte</Text>
            <Text style={[styles.themeOptionSubtitle, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, fontScale.scale), lineHeight: scaleLineHeight(18, fontScale.scale) }]}>Réglez rapidement la taille des polices de l'interface.</Text>
          </View>
          <View style={styles.fontSizeActions}>
            <Pressable
              testID="settings-font-size-decrease"
              accessibilityLabel="Diminuer la taille du texte"
              disabled={!fontScale.canDecrease}
              onPress={decreaseFontSize}
              style={[styles.fontSizeButton, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }, !fontScale.canDecrease && styles.optionDisabled]}
            >
              <Feather name="zoom-out" size={18} color={theme.colors.text} />
            </Pressable>
            <StatusPill label={`Taille: ${formatFontSizeModeLabel(fontScale.mode)}`} tone="neutral" />
            <Pressable
              testID="settings-font-size-increase"
              accessibilityLabel="Agrandir la taille du texte"
              disabled={!fontScale.canIncrease}
              onPress={increaseFontSize}
              style={[styles.fontSizeButton, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }, !fontScale.canIncrease && styles.optionDisabled]}
            >
              <Feather name="zoom-in" size={18} color={theme.colors.text} />
            </Pressable>
          </View>
        </View>
        <View style={styles.themeGrid}>
          {themeOptions.map((option) => {
            const selected = themeMode === option.value;

            return (
              <Pressable
                key={option.value}
                onPress={() => setThemeMode(option.value)}
                style={[
                  styles.themeOption,
                  {
                    backgroundColor: selected ? theme.colors.selection : theme.colors.surfaceMuted,
                    borderColor: selected ? theme.colors.primary : theme.colors.border,
                  },
                ]}
              >
                <Text style={[styles.themeOptionTitle, { color: theme.colors.text, fontSize: scaleFontSize(16, fontScale.scale) }]}>{option.title}</Text>
                <Text style={[styles.themeOptionSubtitle, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, fontScale.scale), lineHeight: scaleLineHeight(18, fontScale.scale) }]}>{option.subtitle}</Text>
              </Pressable>
            );
          })}
        </View>
      </SectionCard>
      <SectionCard title="Runtime visible">
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>LLM: {data?.llmAvailable ? 'disponible' : 'indisponible'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Provider LLM: {data?.runtime?.llmProvider ?? '-'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Modele actif: {data?.runtime?.llmModel ?? 'en attente'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Provider Euria: {data?.runtime?.euriaProvider ?? 'Infomaniak'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Modele Euria: {data?.runtime?.euriaModel ?? 'openai/gpt-oss-120b'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Embeddings: {data?.runtime?.embeddingModel ?? '-'}</Text>
        <StatusPill label={autolearnLabel} tone={autolearnTone} />
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Gestion auto-learn: {data?.autolearn?.managedBy ?? '-'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>PID worker: {data?.autolearn?.pid ?? '-'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Etape: {data?.autolearn?.step ?? '-'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Debut worker: {formatTimestamp(data?.autolearn?.startedAt)}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Derniere maj: {formatTimestamp(data?.autolearn?.updatedAt)}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Prochain cycle: {formatTimestamp(data?.autolearn?.nextRunAt)}</Text>
      </SectionCard>
      <SectionCard
        title="ChromaDB"
        subtitle="Etat de l'index vectoriel local et relance manuelle de l'indexation du coffre."
        headerAccessory={<StatusPill label={indexingLabel} tone={indexingTone} />}
      >
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Moteur vectoriel: {data?.runtime?.vectorStore ?? 'ChromaDB'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Notes indexees: {data?.notesIndexed ?? '-'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Chunks stockes: {data?.chunksIndexed ?? '-'}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Progression: {data?.indexing?.processed ?? 0} / {data?.indexing?.total ?? 0}</Text>
        <Text style={[styles.bodyText, { color: theme.colors.text, fontSize: scaleFontSize(14, fontScale.scale), lineHeight: scaleLineHeight(20, fontScale.scale) }]}>Etape courante: {data?.indexing?.current || 'Indexation terminee'}</Text>
        <Pressable
          testID="settings-reindex-button"
          disabled={reindexData.isPending || data?.indexing?.running}
          onPress={onReindex}
          style={[
            styles.button,
            { backgroundColor: theme.colors.primary },
            (reindexData.isPending || data?.indexing?.running) && styles.optionDisabled,
          ]}
        >
          <Text style={[styles.buttonText, { color: theme.colors.primaryText, fontSize: scaleFontSize(13, fontScale.scale) }]}>
            {reindexData.isPending ? 'Reindexation en cours...' : 'Reindexer les donnees'}
          </Text>
        </Pressable>
      </SectionCard>
      <SectionCard title="Console" subtitle="Logs applicatifs en temps réel.">
        <LogConsole entries={logEntries} />
      </SectionCard>
    </Screen>
  );
}

function formatTimestamp(value?: string | null) {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('fr-FR');
}

const styles = StyleSheet.create({
  fontSizePanel: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 14,
    gap: 10,
  },
  fontSizeCopy: {
    gap: 4,
  },
  fontSizeActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flexWrap: 'wrap',
  },
  fontSizeButton: {
    width: 42,
    height: 42,
    borderRadius: 999,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  themeGrid: {
    gap: 10,
  },
  optionDisabled: {
    opacity: 0.45,
  },
  themeOption: {
    borderRadius: 16,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 14,
    gap: 4,
  },
  themeOptionTitle: {
    fontSize: 16,
    fontWeight: '800',
  },
  themeOptionSubtitle: {
    fontSize: 12,
    lineHeight: 18,
  },
  bodyText: {
    lineHeight: 20,
  },
  button: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    fontWeight: '700',
  },
  dangerButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  buttonText: {
    fontWeight: '700',
  },
});
