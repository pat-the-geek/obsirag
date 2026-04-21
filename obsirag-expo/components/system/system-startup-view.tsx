import { Pressable, StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';
import { SystemStatus } from '../../types/domain';
import { SectionCard } from '../ui/section-card';
import { StatusPill } from '../ui/status-pill';

type SystemStartupViewProps = {
  startup?: SystemStatus['startup'];
  backendReachable?: boolean;
  llmAvailable?: boolean;
  notesIndexed?: number;
  chunksIndexed?: number;
  loading?: boolean;
  onContinue?: () => void;
  continueLabel?: string;
  compact?: boolean;
};

const DEFAULT_BOOTSTRAP_STEPS = [
  'Initialisation du runtime ObsiRAG',
  'Connexion au backend',
  'Préparation des services applicatifs',
];

export function SystemStartupView({
  startup,
  backendReachable,
  llmAvailable,
  notesIndexed,
  chunksIndexed,
  loading = false,
  onContinue,
  continueLabel = 'Ouvrir l’application',
  compact = false,
}: SystemStartupViewProps) {
  const { scale } = useAppFontScale();
  const theme = useAppTheme();
  const steps = startup?.steps?.length ? startup.steps : DEFAULT_BOOTSTRAP_STEPS;
  const currentStep = startup?.currentStep?.trim() || steps[steps.length - 1] || 'Initialisation en cours';
  const isReady = Boolean(startup?.ready);
  const hasError = Boolean(startup?.error);
  const activeIndex = Math.max(steps.findIndex((step) => step === currentStep), 0);

  const body = (
    <View style={styles.cardContent}>
      <View style={styles.statusRow}>
        <StatusPill
          label={hasError ? 'Démarrage en erreur' : isReady ? 'Système prêt' : loading ? 'Initialisation en cours' : 'Préparation en cours'}
          tone={hasError ? 'danger' : isReady ? 'success' : 'warning'}
        />
        <StatusPill label={backendReachable ? 'Backend connecté' : 'Backend en attente'} tone={backendReachable ? 'success' : 'warning'} />
        <StatusPill label={llmAvailable ? 'LLM disponible' : 'LLM en attente'} tone={llmAvailable ? 'success' : 'warning'} />
      </View>

      <View style={[styles.currentStepCard, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
        <Text style={[styles.currentStepLabel, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>Etape active</Text>
        <Text style={[styles.currentStepValue, { color: theme.colors.text, fontSize: scaleFontSize(16, scale), lineHeight: scaleLineHeight(22, scale) }]}>{hasError ? startup?.error : currentStep}</Text>
      </View>

      <View style={styles.metricsRow}>
        <View style={[styles.metricChip, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <Text style={[styles.metricValue, { color: theme.colors.text, fontSize: scaleFontSize(18, scale) }]}>{typeof notesIndexed === 'number' ? notesIndexed : '...'}</Text>
          <Text style={[styles.metricLabel, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>Notes indexées</Text>
        </View>
        <View style={[styles.metricChip, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]}>
          <Text style={[styles.metricValue, { color: theme.colors.text, fontSize: scaleFontSize(18, scale) }]}>{typeof chunksIndexed === 'number' ? chunksIndexed : '...'}</Text>
          <Text style={[styles.metricLabel, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>Chunks prêts</Text>
        </View>
      </View>

      <View style={styles.stepsList}>
        {steps.map((step, index) => {
          const isLast = index === steps.length - 1;
          const isActive = !hasError && !isReady && step === currentStep;
          const isCompleted = isReady || index < activeIndex;

          return (
            <View key={`${index}-${step}`} style={styles.stepRow}>
              <View
                style={[
                  styles.stepDot,
                  { backgroundColor: theme.colors.textSubtle },
                  isReady && isLast ? styles.stepDotReady : null,
                  isActive ? styles.stepDotActive : null,
                  isCompleted ? styles.stepDotDone : null,
                ]}
              />
              <Text
                style={[
                  styles.stepText,
                  { color: theme.colors.textMuted, fontSize: scaleFontSize(14, scale), lineHeight: scaleLineHeight(20, scale) },
                  isActive ? [styles.stepTextActive, { color: theme.colors.text }] : null,
                  isCompleted && !isActive ? { color: theme.colors.text } : null,
                ]}
              >
                {step}
              </Text>
            </View>
          );
        })}
      </View>

      {(isReady || hasError) && onContinue ? (
        <Pressable style={[styles.continueButton, { backgroundColor: theme.colors.primary }]} onPress={onContinue}>
          <Text style={[styles.continueLabel, { color: theme.colors.primaryText, fontSize: scaleFontSize(13, scale) }]}>{continueLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );

  if (compact) {
    return body;
  }

  return (
    <View style={styles.shell}>
      <View style={styles.hero}>
        <Text style={[styles.eyebrow, { color: theme.colors.primary, fontSize: scaleFontSize(12, scale) }]}>ObsiRAG</Text>
        <Text style={[styles.title, { color: theme.colors.text, fontSize: scaleFontSize(30, scale) }]}>Préparation du système</Text>
        <Text style={[styles.subtitle, { color: theme.colors.textMuted, fontSize: scaleFontSize(15, scale), lineHeight: scaleLineHeight(22, scale) }]}>Chargement du backend, des composants d’indexation, du graphe, de l’auto-learner et du runtime LLM avant l’ouverture de l’application.</Text>
      </View>

      <SectionCard title="Etat de préparation" subtitle="Cette séquence reprend les étapes techniques nécessaires au démarrage du runtime.">
        {body}
      </SectionCard>
    </View>
  );
}

const styles = StyleSheet.create({
  shell: {
    gap: 18,
  },
  hero: {
    gap: 8,
    paddingTop: 20,
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  title: {
    fontSize: 30,
    fontWeight: '800',
  },
  subtitle: {
    fontSize: 15,
    lineHeight: 22,
    maxWidth: 760,
  },
  statusRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  currentStepCard: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 14,
    gap: 6,
  },
  currentStepLabel: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  currentStepValue: {
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 22,
  },
  metricsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  metricChip: {
    minWidth: 140,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 3,
  },
  metricValue: {
    fontSize: 18,
    fontWeight: '800',
  },
  metricLabel: {
    fontSize: 12,
  },
  stepsList: {
    gap: 10,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  stepDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginTop: 5,
  },
  stepDotActive: {
    backgroundColor: '#4aa3ff',
  },
  stepDotDone: {
    backgroundColor: '#83ddc6',
  },
  stepDotReady: {
    backgroundColor: '#83ddc6',
  },
  stepText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  stepTextActive: {
    fontWeight: '700',
  },
  continueButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  continueLabel: {
    fontSize: 13,
    fontWeight: '800',
  },
  cardContent: {
    gap: 10,
  },
});