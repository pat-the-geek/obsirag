import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { aggregateConversationEntityContexts, ConversationEntitySidebar } from '../../../components/chat/conversation-entity-sidebar';
import { MessageBubble } from '../../../components/chat/message-bubble';
import { MessageComposer } from '../../../components/chat/message-composer';
import { Screen } from '../../../components/ui/screen';
import { useConversation, useDeleteConversationMessage, useExplicitWebSearch, useGenerateConversationReport, useSaveConversation, useStreamMessage } from '../../../features/chat/use-chat';
import { EntityContext, ChatMessage, SourceRef } from '../../../types/domain';
import { useAppStore } from '../../../store/app-store';
import { useAppTheme } from '../../../theme/app-theme';
import { formatMetadataDate, formatSizeBytes, joinMetadataParts } from '../../../utils/format-display';
import { buildNoteRoute } from '../../../utils/note-route';

const PENDING_ASSISTANT_IDS = new Set(['streaming-assistant', 'pending-web-assistant']);

const DEFAULT_CHAT_SUGGESTIONS = [
  'Resume la note principale sur Artemis II',
  'Quelles connexions utiles vois-tu entre mes notes recentes ?',
  'Cette information est-elle dans mon coffre ou faut-il aller sur le web ?',
  'Propose trois questions pertinentes a partir de mon coffre',
];

export default function ConversationDetailScreen() {
  const insets = useSafeAreaInsets();
  const { height, width } = useWindowDimensions();
  const router = useRouter();
  const params = useLocalSearchParams<{ conversationId: string }>();
  const conversationId = useMemo(
    () => (Array.isArray(params.conversationId) ? params.conversationId[0] : params.conversationId),
    [params.conversationId],
  );
  const draft = useAppStore((state) => (conversationId ? state.drafts[conversationId] ?? '' : ''));
  const setDraft = useAppStore((state) => state.setDraft);
  const useEuriaForConversation = useAppStore((state) => state.useEuriaForConversation);
  const setUseEuriaForConversation = useAppStore((state) => state.setUseEuriaForConversation);
  const theme = useAppTheme();
  const { data, isLoading, isRefetching, refetch } = useConversation(conversationId);
  const messages = data?.messages ?? [];
  const streamMessage = useStreamMessage(conversationId ?? '');
  const explicitWebSearch = useExplicitWebSearch(conversationId ?? '');
  const deleteConversationMessage = useDeleteConversationMessage(conversationId ?? '');
  const saveConversation = useSaveConversation();
  const generateConversationReport = useGenerateConversationReport();
  const pendingAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant' && PENDING_ASSISTANT_IDS.has(item.id)),
    [messages],
  );
  const responseActionPending = streamMessage.isPending || explicitWebSearch.isPending;
  const activeProgressSteps = responseActionPending
    ? (pendingAssistantMessage?.timeline?.length ? pendingAssistantMessage.timeline : ['Réponse en préparation'])
    : [];
  const activeProgressLabel = activeProgressSteps[activeProgressSteps.length - 1] ?? null;
  const latestAssistantMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'assistant'),
    [messages],
  );
  const latestUserMessage = useMemo(
    () => [...messages].reverse().find((item) => item.role === 'user'),
    [messages],
  );
  const hasReportableConversation = useMemo(
    () => messages.some((item) => item.role === 'assistant' && item.content.trim().length > 0),
    [messages],
  );
  const quickActions = useMemo(
    () => DEFAULT_CHAT_SUGGESTIONS.filter((item) => item !== latestUserMessage?.content).slice(0, 4),
    [latestUserMessage?.content],
  );
  const aggregatedEntityContexts = useMemo(() => aggregateConversationEntityContexts(messages), [messages]);
  const [generationActivityFrame, setGenerationActivityFrame] = useState(0);
  const showEntityAside = Platform.OS === 'web' && width >= 1180 && aggregatedEntityContexts.length > 0;
  const showEntityCompact = !showEntityAside && aggregatedEntityContexts.length > 0;
  const asideEntityMaxHeight = Math.max(360, height - Math.max(24, insets.top + 18) - 18);
  const isGenerationStepActive = streamMessage.isPending && activeProgressSteps.some((step) => isGenerationStep(step));
  const scrollRef = useRef<ScrollView | null>(null);
  const conversationMetadata = joinMetadataParts([
    data?.updatedAt ? `Modifie le ${formatMetadataDate(data.updatedAt)}` : null,
    formatSizeBytes(data?.sizeBytes),
  ]);
  const conversationRoute = conversationId ? `/(tabs)/chat/${conversationId}` : '';

  const openNoteFromConversation = (notePath: string) => {
    router.push(buildNoteRoute(notePath, conversationRoute ? { returnTo: conversationRoute } : undefined));
  };

  const scrollThreadToBottom = () => {
    if (process.env.NODE_ENV === 'test' || typeof requestAnimationFrame !== 'function') {
      scrollRef.current?.scrollToEnd({ animated: true });
      return;
    }

    requestAnimationFrame(() => {
      scrollRef.current?.scrollToEnd({ animated: true });
    });
  };

  useEffect(() => {
    if (!isGenerationStepActive) {
      setGenerationActivityFrame(0);
      return undefined;
    }

    const timer = setInterval(() => {
      setGenerationActivityFrame((current) => (current + 1) % GENERATION_ACTIVITY_FRAMES.length);
    }, 220);

    return () => clearInterval(timer);
  }, [isGenerationStepActive]);

  useEffect(() => {
    if (!messages.length) {
      return;
    }
    scrollThreadToBottom();
  }, [messages.length]);

  const confirmDeleteMessage = (messageId: string) => {
    const executeDelete = () =>
      deleteConversationMessage.mutate(messageId, {
        onError: (error) =>
          Alert.alert('Suppression impossible', error instanceof Error ? error.message : 'Erreur inconnue'),
      });

    if (typeof globalThis.confirm === 'function') {
      const confirmed = globalThis.confirm('Cette question et sa réponse seront retirées définitivement de la conversation.');
      if (confirmed) {
        executeDelete();
      }
      return;
    }

    Alert.alert(
      'Supprimer la réponse',
      'Cette question et sa réponse seront retirées définitivement de la conversation.',
      [
        {
          text: 'Annuler',
          style: 'cancel',
        },
        {
          text: 'Supprimer',
          style: 'destructive',
          onPress: executeDelete,
        },
      ],
      { cancelable: true },
    );
  };

  if (!conversationId || isLoading || !data) {
    return (
      <Screen backgroundColor={theme.colors.background}>
        <ActivityIndicator color={theme.colors.primary} />
      </Screen>
    );
  }

  return (
    <Screen scroll scrollRef={scrollRef} refreshing={isRefetching} onRefresh={refetch} backgroundColor={theme.colors.background} contentStyle={styles.screenContent}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={Math.max(12, insets.bottom)} style={styles.keyboardShell}>
      <View style={[styles.shell, { paddingBottom: Math.max(14, insets.bottom + 8) }]}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={[styles.headerTitle, { color: theme.colors.text }]}>{data.title}</Text>
            {conversationMetadata ? <Text style={[styles.headerMeta, { color: theme.colors.textSubtle }]}>{conversationMetadata}</Text> : null}
            <View style={[styles.providerBadge, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }] }>
              <Text style={[styles.providerBadgeLabel, { color: theme.colors.textMuted }]}>Provider actif</Text>
              <Text style={[styles.providerBadgeValue, { color: useEuriaForConversation ? theme.colors.primary : theme.colors.text }]}>
                {useEuriaForConversation ? 'Euria' : 'Local (MLX)'}
              </Text>
            </View>
            <Text style={[styles.headerSubtitle, { color: theme.colors.textMuted }]}>Conversation centree, reponses developpees et actions contextuelles en bas d'ecran.</Text>
          </View>
        </View>

        <View style={[styles.contentLayout, showEntityAside ? styles.contentLayoutWide : null]}>
          <View style={styles.mainColumn}>
            {showEntityCompact ? (
              <ConversationEntitySidebar
                entities={aggregatedEntityContexts}
                compact
                onOpenNote={openNoteFromConversation}
                onOpenTag={(tag) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(tag)}`)}
              />
            ) : null}

            <View style={[styles.thread, { paddingBottom: 28 + insets.bottom }]}>
              {messages.length === 0 ? (
                <View style={[styles.emptyStateCard, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
                  <Text style={[styles.emptyStateTitle, { color: theme.colors.text }]}>Exemples de questions</Text>
                  <Text style={[styles.emptyStateBody, { color: theme.colors.textMuted }]}>Cette vue propose des points d'entree rapides pour lancer un premier tour utile.</Text>
                  <View style={styles.emptyStateActions}>
                    {quickActions.map((item) => (
                      <Pressable key={item} style={[styles.emptyStateActionButton, { backgroundColor: theme.colors.surface, borderColor: theme.colors.border }]} onPress={() => setDraft(conversationId, item)}>
                        <Text style={[styles.emptyStateActionText, { color: theme.colors.text }]}>{item}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              ) : null}
              {messages.map((message, index) => {
                const previousUserQuery = [...messages.slice(0, index)].reverse().find((item) => item.role === 'user')?.content;

                return (
                  <MessageBubble
                    key={message.id}
                    message={message}
                    highlightEntities={aggregatedEntityContexts}
                    onSuggestWebSearch={(query) => explicitWebSearch.mutate(query)}
                    onOpenNote={openNoteFromConversation}
                    onOpenTag={(tag) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(tag)}`)}
                    onOpenPrimarySource={openNoteFromConversation}
                    onDeleteMessage={confirmDeleteMessage}
                    onReusePrompt={(query) => setDraft(conversationId, query)}
                    {...(() => {
                      const webSearchSuggestion = buildMessageWebSearchSuggestion(message, previousUserQuery, messages.slice(0, index), aggregatedEntityContexts);
                      return webSearchSuggestion ? { webSearchSuggestion } : {};
                    })()}
                    {...(previousUserQuery ? { replyPrompt: previousUserQuery } : {})}
                  />
                );
              })}
            </View>

            <View style={[styles.dock, { backgroundColor: theme.colors.background }, Platform.OS === 'web' ? [styles.dockWeb, { borderTopColor: theme.colors.border, shadowColor: theme.colors.shadow }] : null]}>
              {(responseActionPending || generateConversationReport.isPending) ? (
                <View style={[styles.progressCard, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
                  <Text style={[styles.progressTitle, { color: theme.colors.text }]}>Progression du traitement</Text>
                  {activeProgressLabel ? <Text style={[styles.progressCurrent, { color: theme.colors.primary }]}>{activeProgressLabel}</Text> : null}
                  <View style={styles.progressList}>
                    {activeProgressSteps.map((step, index) => {
                      const isLast = index === activeProgressSteps.length - 1;
                      // Afficher la boucle d'activité sur la dernière étape si génération rapport
                      const showGenerationActivity = (isLast && isGenerationStep(step) && isGenerationStepActive) || generateConversationReport.isPending;
                      return (
                        <View key={`${step}-${index}`} style={styles.progressItem}>
                          <View style={[styles.progressDot, { backgroundColor: theme.colors.textSubtle }, isLast ? [styles.progressDotActive, { backgroundColor: theme.colors.primary }] : null]} />
                          <View style={styles.progressTextRow}>
                            <Text style={[styles.progressText, { color: theme.colors.textMuted }, isLast ? [styles.progressTextActive, { color: theme.colors.text }] : null]}>{step}</Text>
                            <Text style={[styles.progressActivityGlyph, showGenerationActivity ? [styles.progressActivityGlyphActive, { color: theme.colors.primary }] : null]}>
                              {showGenerationActivity ? GENERATION_ACTIVITY_FRAMES[generationActivityFrame] : ' '}
                            </Text>
                          </View>
                        </View>
                      );
                    })}
                  </View>
                </View>
              ) : null}
              {explicitWebSearch.isPending ? <Text style={[styles.statusText, { color: theme.colors.textMuted }]}>Recherche sur le web en cours...</Text> : null}
              {streamMessage.error ? (
                <Text style={[styles.errorText, { color: theme.colors.warningText }] }>
                  Erreur: {streamMessage.error instanceof Error ? streamMessage.error.message : 'generation indisponible'}
                </Text>
              ) : null}

              <MessageComposer
                value={draft}
                onChangeText={(value) => setDraft(conversationId, value)}
                withEuria={useEuriaForConversation}
                onToggleWithEuria={setUseEuriaForConversation}
                onSubmit={(submittedValue) => {
                  const trimmedDraft = submittedValue.trim();
                  if (!trimmedDraft) {
                    return;
                  }
                  scrollThreadToBottom();
                  streamMessage.mutate(trimmedDraft);
                }}
                secondaryActionLabel="Sauvegarder"
                onSecondaryAction={() => {
                  if (!conversationId) {
                    return;
                  }
                  saveConversation.mutate(conversationId, {
                    onSuccess: (result) => Alert.alert('Conversation sauvegardee', result.path),
                    onError: (error) => Alert.alert('Sauvegarde impossible', error instanceof Error ? error.message : 'Erreur inconnue'),
                  });
                }}
                secondaryActionDisabled={saveConversation.isPending}
                onTertiaryAction={() => {
                  if (!conversationId) {
                    return;
                  }
                  generateConversationReport.mutate(conversationId, {
                    onSuccess: (result) => openNoteFromConversation(result.path),
                    onError: (error) => Alert.alert('Rapport impossible', error instanceof Error ? error.message : 'Erreur inconnue'),
                  });
                }}
                tertiaryActionDisabled={generateConversationReport.isPending}
                disabled={streamMessage.isPending}
                {...(hasReportableConversation ? { tertiaryActionLabel: 'Rapport' } : {})}
              />
            </View>
          </View>

          {showEntityAside ? (
            <ConversationEntitySidebar
              entities={aggregatedEntityContexts}
              maxHeight={asideEntityMaxHeight}
              onOpenNote={openNoteFromConversation}
              onOpenTag={(tag) => router.push(`/(tabs)/graph?tag=${encodeURIComponent(tag)}`)}
            />
          ) : null}
        </View>
      </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function buildMessageWebSearchSuggestion(
  message: ChatMessage,
  userQuery: string | undefined,
  previousMessages: ChatMessage[],
  fallbackEntities: EntityContext[],
) {
  const contextualSuggestion = buildWebSearchSuggestion(userQuery, previousMessages, fallbackEntities);
  if (contextualSuggestion) {
    return contextualSuggestion;
  }

  const queryOverviewSearch = message.queryOverview?.searchQuery?.trim();
  if (queryOverviewSearch) {
    return queryOverviewSearch;
  }

  const queryOverviewQuery = message.queryOverview?.query?.trim();
  if (queryOverviewQuery) {
    const derivedFromOverview = buildWebSearchSuggestion(queryOverviewQuery, previousMessages, fallbackEntities);
    if (derivedFromOverview) {
      return derivedFromOverview;
    }
    return queryOverviewQuery;
  }

  const messageEntities = [...(message.entityContexts ?? []), ...fallbackEntities];
  const preferredSubject = selectPreferredSubject(messageEntities);
  if (preferredSubject) {
    const enrichmentTerms = defaultEnrichmentTerms(`Parle moi de ${preferredSubject.value}`, preferredSubject);
    return [preferredSubject.value, ...enrichmentTerms].filter(Boolean).join(' ');
  }

  const primarySourceTitle = message.primarySource?.noteTitle?.trim();
  if (primarySourceTitle) {
    return primarySourceTitle;
  }

  return undefined;
}

const styles = StyleSheet.create({
  keyboardShell: {
    width: '100%',
  },
  screenContent: {
    paddingHorizontal: 0,
    paddingTop: 0,
    gap: 0,
  },
  shell: {
    width: '100%',
    maxWidth: 1260,
    alignSelf: 'center',
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 14,
    gap: 14,
  },
  contentLayout: {
    gap: 14,
  },
  contentLayoutWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  mainColumn: {
    flex: 1,
    minWidth: 0,
    gap: 14,
  },
  header: {
    gap: 12,
  },
  headerCopy: {
    gap: 6,
  },
  headerTitle: {
    fontSize: 22,
    fontWeight: '700',
  },
  headerSubtitle: {
    lineHeight: 20,
  },
  headerMeta: {
    fontSize: 12,
    lineHeight: 18,
  },
  providerBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  providerBadgeLabel: {
    fontSize: 12,
    fontWeight: '600',
  },
  providerBadgeValue: {
    fontSize: 12,
    fontWeight: '800',
  },
  thread: {
    paddingTop: 12,
    gap: 18,
  },
  emptyStateCard: {
    borderRadius: 18,
    borderWidth: 1,
    padding: 16,
    gap: 10,
  },
  emptyStateTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  emptyStateBody: {
    lineHeight: 20,
  },
  emptyStateActions: {
    gap: 8,
  },
  emptyStateActionButton: {
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  emptyStateActionText: {
    lineHeight: 20,
  },
  dock: {
    flexShrink: 0,
    gap: 10,
    paddingTop: 8,
  },
  dockWeb: {
    position: 'sticky' as 'absolute',
    bottom: 0,
    zIndex: 10,
    paddingBottom: 12,
    borderTopWidth: 1,
    shadowOpacity: 0.08,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: -6 },
  },
  progressCard: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 12,
    gap: 8,
  },
  progressTitle: {
    fontSize: 13,
    fontWeight: '700',
  },
  progressCurrent: {
    fontSize: 13,
    fontWeight: '600',
  },
  progressList: {
    gap: 6,
  },
  progressItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  progressTextRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minWidth: 0,
  },
  progressDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  progressDotActive: {},
  progressText: {
    fontSize: 13,
  },
  progressTextActive: {
    fontWeight: '600',
  },
  progressActivityGlyph: {
    width: 10,
    color: 'transparent',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  progressActivityGlyphActive: {},
  errorText: {
    fontSize: 13,
  },
  statusText: {
    fontSize: 13,
  },
});

const GENERATION_ACTIVITY_FRAMES = ['-', 'x', 'o', '!'] as const;

const WEB_SEARCH_STOPWORDS = new Set([
  'quel', 'quelle', 'quels', 'quelles', 'est', 'sont', 'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'au', 'aux',
  'dans', 'sur', 'pour', 'avec', 'sans', 'et', 'ou', 'où', 'que', 'quoi', 'qui', 'comment', 'pourquoi', 'combien',
  'son', 'sa', 'ses', 'leur', 'leurs', 'il', 'elle', 'ils', 'elles', 'lui', 'en', 'a', 't', 'tu', 'je', 'j', 'nous', 'vous',
  'me', 'moi', 'te', 'toi', 'ce', 'cet', 'cette', 'ces', 'cela', 'ca', 'ça', 'd', 'l', 'y', 'on', 'se', 'si', 'plus', 'moins',
  'parle', 'parler', 'dis', 'dire', 'explique', 'expliquer', 'presente', 'présente', 'presenter', 'présenter',
  'recherche', 'rechercher', 'web', 'information', 'informations', 'infos',
]);

const WEB_SEARCH_ASPECT_MAP: Record<string, string> = {
  salaire: 'salary',
  salaires: 'salary',
  revenu: 'revenue',
  revenus: 'revenue',
  fortune: 'net worth',
  richesse: 'net worth',
  age: 'age',
  âge: 'age',
  taille: 'height',
  poids: 'weight',
  action: 'stock',
  actions: 'stock',
  bourse: 'stock',
  cours: 'stock',
  entreprise: 'company',
  societe: 'company',
  société: 'company',
  femme: 'wife',
  epouse: 'wife',
  épouse: 'wife',
  mari: 'husband',
  conjoint: 'spouse',
  enfants: 'children',
  enfant: 'child',
  nationalite: 'nationality',
  nationalité: 'nationality',
};

const WEB_SEARCH_DYNAMIC_TERMS = new Set(['salary', 'revenue', 'net worth', 'stock', 'price', 'age']);
const WEB_SEARCH_GENERIC_INTRO_RE = /^(?:que\s+sais[- ]?tu\s+de|parle(?:[- ]?moi)?\s+de|dis(?:[- ]?moi)?\s+.+?\s+de|explique(?:[- ]?moi)?|presente(?:[- ]?moi)?|présente(?:[- ]?moi)?)/i;
const WEB_SEARCH_EXPLICIT_SUBJECT_PATTERNS = [
  /^(?:recherche(?:r)?\s+sur\s+le\s+web(?:\s+des)?\s+informations?\s+sur)\s+(.+)$/i,
  /^(?:recherche(?:r)?(?:\s+des)?\s+informations?\s+sur)\s+(.+)$/i,
  /^(?:parle(?:[- ]?moi)?\s+de)\s+(.+)$/i,
  /^(?:que\s+sais[- ]?tu\s+de)\s+(.+)$/i,
  /^(?:présente(?:[- ]?moi)?|presente(?:[- ]?moi)?|explique(?:[- ]?moi)?)\s+(.+)$/i,
];

const WEB_SEARCH_DEFAULT_ENRICHMENT_TERMS: Record<string, string[]> = {
  person: ['biography', 'career', 'latest'],
  organization: ['company', 'overview', 'latest'],
  location: ['overview', 'history'],
  date: ['timeline', 'context'],
  time: ['timeline', 'context'],
  concept: ['overview', 'definition'],
};

function buildWebSearchSuggestion(userQuery: string | undefined, previousMessages: ChatMessage[], fallbackEntities: EntityContext[]) {
  if (!userQuery?.trim()) {
    return undefined;
  }

  const recentEntities = collectRecentEntities(previousMessages, fallbackEntities);
  const normalizedQuestion = userQuery.trim().replace(/\s+/g, ' ');
  const explicitSubject = resolveExplicitSubject(normalizedQuestion, recentEntities);
  const preferredSubject = explicitSubject ?? selectPreferredSubject(recentEntities);
  const aspectTerms = extractWebAspectTerms(normalizedQuestion, preferredSubject);
  const needsContextualSubject = !explicitSubject && questionNeedsContextualSubject(normalizedQuestion);
  const basedOnQuestionParts = [explicitSubject?.value, ...aspectTerms];
  const dedupedQuestionParts = [...new Set(basedOnQuestionParts.map((part) => part?.trim()).filter((part): part is string => Boolean(part)))];

  if (!needsContextualSubject && dedupedQuestionParts.length) {
    if (!/\b(19|20)\d{2}\b/.test(normalizedQuestion) && dedupedQuestionParts.some((part) => WEB_SEARCH_DYNAMIC_TERMS.has(part))) {
      dedupedQuestionParts.push(String(new Date().getFullYear()));
    }

    return dedupedQuestionParts.join(' ');
  }

  if (preferredSubject && needsContextualSubject) {
    const contextualParts = [preferredSubject.value, ...aspectTerms];
    const dedupedContextualParts = [...new Set(contextualParts.map((part) => part.trim()).filter(Boolean))];

    if (!dedupedContextualParts.length) {
      return preferredSubject.value;
    }

    if (!/\b(19|20)\d{2}\b/.test(normalizedQuestion) && dedupedContextualParts.some((part) => WEB_SEARCH_DYNAMIC_TERMS.has(part))) {
      dedupedContextualParts.push(String(new Date().getFullYear()));
    }

    return dedupedContextualParts.join(' ');
  }

  if (!normalizedQuestion) {
    return normalizedQuestion;
  }

  return normalizedQuestion;
}

function questionNeedsContextualSubject(question: string) {
  const normalized = normalizeSearchText(question);
  if (!normalized) {
    return false;
  }

  return /\b(son|sa|ses|sont|lui|elle|il|ils|elles|leur|leurs|ce|cet|cette|ces|cela|ca|ça|en)\b/.test(normalized);
}

function isGenerationStep(step: string) {
  const normalized = step.trim().toLocaleLowerCase('fr');
  return normalized.includes('generation de la reponse') || normalized.includes('réponse générée') || normalized.includes('reponse generee');
}

function resolveExplicitSubject(question: string, entities: EntityContext[]) {
  const explicitSubject = extractExplicitSubject(question);
  if (!explicitSubject) {
    return undefined;
  }

  const normalizedExplicit = normalizeSearchText(explicitSubject);
  const matchedEntity = entities.find((entity) => {
    const normalizedEntity = normalizeSearchText(entity.value);
    return normalizedEntity === normalizedExplicit || normalizedEntity.includes(normalizedExplicit) || normalizedExplicit.includes(normalizedEntity);
  });

  if (matchedEntity) {
    return {
      ...matchedEntity,
      value: explicitSubject,
    };
  }

  return {
    type: 'concept',
    typeLabel: 'Sujet',
    value: explicitSubject,
    notes: [],
  };
}

function extractExplicitSubject(question: string) {
  const normalizedQuestion = question.trim();
  for (const pattern of WEB_SEARCH_EXPLICIT_SUBJECT_PATTERNS) {
    const match = normalizedQuestion.match(pattern);
    const candidate = match?.[1]?.trim();
    if (candidate) {
      return cleanExplicitSubject(candidate);
    }
  }
  return undefined;
}

function cleanExplicitSubject(value: string) {
  return value.replace(/[?.!,;:]+$/g, '').trim();
}

function normalizeSearchText(value: string) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLocaleLowerCase('fr')
    .replace(/[^a-z0-9\s-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function collectRecentEntities(previousMessages: ChatMessage[], fallbackEntities: EntityContext[]) {
  const collected: EntityContext[] = [];
  const seen = new Set<string>();

  for (let index = previousMessages.length - 1; index >= 0; index -= 1) {
    for (const entity of previousMessages[index]?.entityContexts ?? []) {
      const key = entity.value.trim().toLocaleLowerCase('fr');
      if (!key || seen.has(key)) {
        continue;
      }
      seen.add(key);
      collected.push(entity);
    }

    const primarySource = previousMessages[index]?.primarySource;
    const sourceTitle = primarySource?.noteTitle?.trim();
    const sourceKey = sourceTitle?.toLocaleLowerCase('fr');
    if (sourceTitle && sourceKey && !seen.has(sourceKey)) {
      seen.add(sourceKey);
      collected.push({
        value: sourceTitle,
        type: inferEntityTypeFromSource(primarySource),
        typeLabel: 'Sujet',
        notes: primarySource?.filePath ? [{ title: sourceTitle, filePath: primarySource.filePath }] : [],
      });
    }
  }

  for (const entity of fallbackEntities) {
    const key = entity.value.trim().toLocaleLowerCase('fr');
    if (!key || seen.has(key)) {
      continue;
    }
    seen.add(key);
    collected.push(entity);
  }

  return collected;
}

function extractWebAspectTerms(question: string, subject?: EntityContext) {
  const tokens = question.match(/[A-Za-zÀ-ÿ0-9-]+/g) ?? [];
  const terms: string[] = [];
  const subjectTokens = new Set((subject?.value.match(/[A-Za-zÀ-ÿ0-9-]+/g) ?? []).map((token) => token.toLocaleLowerCase('fr')));

  for (const rawToken of tokens) {
    const token = rawToken.trim();
    const low = token.toLocaleLowerCase('fr');
    if (!low || WEB_SEARCH_STOPWORDS.has(low)) {
      continue;
    }
    if (subjectTokens.has(low)) {
      continue;
    }
    if (token.length < 3 && !/^\d{4}$/.test(token)) {
      continue;
    }
    terms.push(WEB_SEARCH_ASPECT_MAP[low] ?? token);
  }

  return terms;
}

function selectPreferredSubject(entities: EntityContext[]) {
  const sorted = [...entities].sort((left, right) => {
    const typeDelta = entityTypeWeight(right.type) - entityTypeWeight(left.type);
    if (typeDelta !== 0) {
      return typeDelta;
    }
    const mentionDelta = (right.mentions ?? 0) - (left.mentions ?? 0);
    if (mentionDelta !== 0) {
      return mentionDelta;
    }
    return left.value.localeCompare(right.value, 'fr', { sensitivity: 'base' });
  });

  return sorted[0];
}

function entityTypeWeight(type: string) {
  const normalized = type.trim().toLocaleLowerCase('fr');
  if (normalized.includes('person')) {
    return 5;
  }
  if (normalized.includes('org')) {
    return 4;
  }
  if (normalized.includes('loc') || normalized.includes('place') || normalized.includes('geo')) {
    return 3;
  }
  if (normalized.includes('date') || normalized.includes('time')) {
    return 2;
  }
  return 1;
}

function inferEntityTypeFromSource(primarySource?: SourceRef | null) {
  const title = primarySource?.noteTitle?.trim() ?? '';
  if (/^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$/.test(title)) {
    return 'person';
  }
  return 'concept';
}

function defaultEnrichmentTerms(question: string, subject?: EntityContext) {
  const normalizedQuestion = question.trim();
  const lowered = normalizedQuestion.toLocaleLowerCase('fr');
  const genericQuestion = WEB_SEARCH_GENERIC_INTRO_RE.test(normalizedQuestion) || /^qui\b|^quoi\b|^que\b|^quel\b|^quelle\b/i.test(normalizedQuestion);
  if (!genericQuestion || !subject) {
    return [];
  }

  const typeKey = normalizeEntityTypeKey(subject.type);
  const defaults = WEB_SEARCH_DEFAULT_ENRICHMENT_TERMS[typeKey] ?? WEB_SEARCH_DEFAULT_ENRICHMENT_TERMS.concept ?? [];

  if (lowered.includes('actualit') || lowered.includes('recent') || lowered.includes('récent') || lowered.includes('202')) {
    return [...defaults.filter((term) => term !== 'latest'), 'latest'];
  }

  return defaults;
}

function normalizeEntityTypeKey(type: string) {
  const normalized = type.trim().toLocaleLowerCase('fr');
  if (normalized.includes('person')) {
    return 'person';
  }
  if (normalized.includes('org')) {
    return 'organization';
  }
  if (normalized.includes('loc') || normalized.includes('place') || normalized.includes('geo')) {
    return 'location';
  }
  if (normalized.includes('date')) {
    return 'date';
  }
  if (normalized.includes('time')) {
    return 'time';
  }
  return 'concept';
}
