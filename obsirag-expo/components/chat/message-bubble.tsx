import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';

import { scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';
import { ChatMessage, EntityContext } from '../../types/domain';
import { MarkdownNote, renderEntityHighlightedText } from '../notes/markdown-note';
import { EntityContextList } from './entity-context-list';
import { SourceList } from './source-list';

type MessageBubbleProps = {
  message: ChatMessage;
  highlightEntities?: EntityHighlightDefinition[];
  onOpenNote?: (notePath: string) => void;
  onOpenTag?: (tag: string) => void;
  onSuggestWebSearch?: (query: string) => void;
  webSearchSuggestion?: string;
  onUseQueryInChat?: (query: string) => void;
  replyPrompt?: string;
  onReusePrompt?: (query: string) => void;
  onOpenPrimarySource?: (notePath: string) => void;
  onDeleteMessage?: (messageId: string) => void;
};

type EntityHighlightDefinition = Pick<EntityContext, 'value' | 'type'>;

export function MessageBubble({
  message,
  highlightEntities,
  onOpenNote,
  onOpenTag,
  onSuggestWebSearch,
  webSearchSuggestion,
  onUseQueryInChat,
  replyPrompt,
  onReusePrompt,
  onOpenPrimarySource,
  onDeleteMessage,
}: MessageBubbleProps) {
  const theme = useAppTheme();
  const { scale } = useAppFontScale();
  const isUser = message.role === 'user';
  const revealProgress = useRef(new Animated.Value(isUser || process.env.NODE_ENV === 'test' ? 1 : 0)).current;
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [entityContextsOpen, setEntityContextsOpen] = useState(true);
  const hasRenderableQueryOverview = isRenderableQueryOverview(message);
  const hasMermaidContent = containsMermaidFence(message.content);
  const shouldHideAssistantMainBubble = Boolean(
    !isUser && hasRenderableQueryOverview && !hasMermaidContent && (message.sentinel || message.provenance === 'web'),
  );
  const shouldRenderQueryOverviewBubble = Boolean(!isUser && hasRenderableQueryOverview && (message.sentinel || message.provenance === 'web'));
  const isPendingAssistant = Boolean(!isUser && (message.id === 'streaming-assistant' || message.id === 'pending-web-assistant'));
  const showWebSearchAction = Boolean(!isUser && !isPendingAssistant && webSearchSuggestion && onSuggestWebSearch);
  const showDeleteAction = Boolean(!isUser && !isPendingAssistant && onDeleteMessage);
  const ddgMarkdown = buildDdgMarkdown(message);
  const providerLabel = formatProviderLabel(message.llmProvider);
  const provenanceLabel = formatProvenanceLabel(message.provenance);
  const targetAssistantContent = shouldHideAssistantMainBubble ? ddgMarkdown : message.content;
  const statsLabel = !isUser && !isPendingAssistant ? formatGenerationStats(message.stats) : null;
  const displayedAssistantContent = targetAssistantContent;
  const displayedQueryOverviewContent = ddgMarkdown;
  const usesPostResponseVaultReferences = Boolean(
    !isUser &&
    message.provenance === 'web' &&
    message.enrichmentPath === 'euria-direct-web' &&
    message.sources?.length,
  );
  const [pendingFrameIndex, setPendingFrameIndex] = useState(0);
  const assistantTone = theme.isDark ? 'dark' : 'light';
  const userBubbleBackground = theme.isDark ? theme.colors.primaryMuted : '#191919';
  const userBubbleBorder = theme.isDark ? theme.colors.primary : '#2d2d2d';
  const userTextColor = theme.isDark ? theme.colors.primaryText : '#f1f1f1';
  const assistantBubbleBackground = theme.colors.surface;
  const assistantBubbleBorder = theme.colors.border;
  const queryOverviewBackground = theme.colors.surfaceMuted;
  const queryOverviewBorder = theme.colors.border;

  useEffect(() => {
    if (isUser || process.env.NODE_ENV === 'test') {
      revealProgress.setValue(1);
      return undefined;
    }

    revealProgress.setValue(0);
    const animation = Animated.timing(revealProgress, {
      toValue: 1,
      duration: 420,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: true,
    });

    animation.start();
    return () => animation.stop();
  }, [isUser, message.id, revealProgress]);

  useEffect(() => {
    if (process.env.NODE_ENV === 'test' || !isPendingAssistant || targetAssistantContent.trim()) {
      setPendingFrameIndex(0);
      return undefined;
    }

    const timer = setInterval(() => {
      setPendingFrameIndex((current) => (current + 1) % PENDING_RESPONSE_FRAMES.length);
    }, 220);

    return () => clearInterval(timer);
  }, [isPendingAssistant, targetAssistantContent]);

  const assistantRevealStyle = !isUser
    ? {
        opacity: revealProgress,
        transform: [
          {
            translateY: revealProgress.interpolate({
              inputRange: [0, 1],
              outputRange: [28, 0],
            }),
          },
        ],
      }
    : null;

  return (
    <View style={[styles.stack, isUser ? styles.userStack : styles.assistantStack]}>
      {!shouldHideAssistantMainBubble ? (
        <Animated.View
          testID={isUser ? 'user-message-shell' : 'assistant-reveal-shell'}
          style={[assistantRevealStyle, isUser ? styles.userBubbleShell : null]}
        >
          <View
            testID={isUser ? 'user-message-bubble' : 'assistant-message-bubble'}
            style={[
              styles.base,
              isUser
                ? [styles.userBubble, { backgroundColor: userBubbleBackground, borderColor: userBubbleBorder }]
                : [styles.assistantBubble, { backgroundColor: assistantBubbleBackground, borderColor: assistantBubbleBorder }],
            ]}
          >
            {!isUser ? (
              <View style={styles.assistantHeader}>
                <Text style={[styles.assistantRole, styles.role, { color: theme.colors.text, fontSize: scaleFontSize(12, scale) }]}>ObsiRAG</Text>
                <View style={styles.assistantBadgeRow}>
                  {provenanceLabel ? (
                    <View
                      testID="message-provenance-badge"
                      style={[styles.providerBadge, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}
                    >
                      <Text style={[styles.providerBadgeText, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>{provenanceLabel}</Text>
                    </View>
                  ) : null}
                  {providerLabel ? (
                    <View style={[styles.providerBadge, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
                      <Text style={[styles.providerBadgeText, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>{providerLabel}</Text>
                    </View>
                  ) : null}
                </View>
              </View>
            ) : null}
            {isUser ? (
              <Text style={[styles.userContent, { color: userTextColor, fontSize: scaleFontSize(15, scale), lineHeight: scaleLineHeight(22, scale) }]}>{renderEntityHighlightedText(message.content, 'dark', highlightEntities, undefined, `user-${message.id}`, theme)}</Text>
            ) : isPendingAssistant && !displayedAssistantContent.trim() ? (
              <View testID="assistant-pending-state" style={styles.pendingState}>
                <View style={styles.pendingTitleRow}>
                  <Text style={[styles.pendingTitle, { color: theme.colors.text, fontSize: scaleFontSize(15, scale) }]}>Réponse en préparation</Text>
                  <Text style={[styles.pendingGlyph, { color: theme.colors.textSubtle, fontSize: scaleFontSize(16, scale) }]}>{PENDING_RESPONSE_FRAMES[pendingFrameIndex]}</Text>
                </View>
                <Text style={[styles.pendingCaption, { color: theme.colors.textMuted, fontSize: scaleFontSize(13, scale), lineHeight: scaleLineHeight(18, scale) }]}>{message.timeline?.[message.timeline.length - 1] ?? 'Traitement en cours'}</Text>
              </View>
            ) : (
              <MarkdownNote
                markdown={displayedAssistantContent}
                variant="article"
                tone={assistantTone}
                {...(highlightEntities ? { entityHighlights: highlightEntities } : {})}
                {...(onOpenNote ? { onOpenNote } : {})}
                {...(onOpenTag ? { onOpenTag } : {})}
              />
            )}
            {!isUser && message.entityContexts?.length ? (
              <EntityContextList
                entities={message.entityContexts}
                isOpen={entityContextsOpen}
                onToggleOpen={() => setEntityContextsOpen((current) => !current)}
              />
            ) : null}
          </View>
        </Animated.View>
      ) : null}
      {!isUser && shouldRenderQueryOverviewBubble ? (
        <Animated.View style={assistantRevealStyle}>
          <View
            testID="message-query-overview-response"
            style={[styles.base, styles.followUpBubble, { backgroundColor: assistantBubbleBackground, borderColor: assistantBubbleBorder }]}
          >
            <View style={styles.followUpHeader}>
              <View style={styles.followUpMeta}>
                <Text style={[styles.assistantRole, styles.role, { color: theme.colors.text, fontSize: scaleFontSize(12, scale) }]}>ObsiRAG</Text>
                {provenanceLabel ? (
                  <View
                    testID="message-provenance-badge"
                    style={[styles.providerBadge, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}
                  >
                    <Text style={[styles.providerBadgeText, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>{provenanceLabel}</Text>
                  </View>
                ) : null}
                {providerLabel ? (
                  <View style={[styles.providerBadge, { backgroundColor: theme.colors.surfaceMuted, borderColor: theme.colors.border }]}>
                    <Text style={[styles.providerBadgeText, { color: theme.colors.textMuted, fontSize: scaleFontSize(11, scale) }]}>{providerLabel}</Text>
                  </View>
                ) : null}
              </View>
              <Text style={[styles.followUpLabel, { color: theme.colors.textMuted, fontSize: scaleFontSize(12, scale) }]}>Vue d'ensemble DDG</Text>
            </View>
            <View style={[styles.queryOverviewBox, { backgroundColor: queryOverviewBackground, borderColor: queryOverviewBorder }]}>
              <MarkdownNote
                markdown={displayedQueryOverviewContent}
                tone={assistantTone}
                {...(highlightEntities ? { entityHighlights: highlightEntities } : {})}
                {...(onOpenNote ? { onOpenNote } : {})}
                {...(onOpenTag ? { onOpenTag } : {})}
              />
            </View>
          </View>
        </Animated.View>
      ) : null}
      {!isUser && message.sources?.length ? (
        <Animated.View style={assistantRevealStyle}>
          <SourceList
            sources={message.sources}
            isOpen={sourcesOpen}
            onToggleOpen={() => setSourcesOpen((current) => !current)}
            onSelectSource={(source) => onOpenNote?.(source.filePath)}
            {...(usesPostResponseVaultReferences ? { title: 'Références coffre', caption: 'Notes associées après la réponse' } : {})}
          />
        </Animated.View>
      ) : null}
      {showWebSearchAction || showDeleteAction ? (
        <View style={styles.actionRow}>
          {showDeleteAction ? (
            <Pressable
              testID="message-delete-action"
              style={[styles.deleteActionButton, { backgroundColor: theme.colors.dangerSurface, borderColor: theme.colors.danger }]}
              onPress={() => onDeleteMessage?.(message.id)}
            >
              <Text style={[styles.deleteActionLabel, { color: theme.colors.dangerPillText, fontSize: scaleFontSize(12, scale) }]}>Supprimer la réponse</Text>
            </Pressable>
          ) : null}
          {showWebSearchAction ? (
            <Pressable
              testID="message-web-search-action"
              style={[styles.webSearchActionButton, { backgroundColor: theme.colors.warningSurface, borderColor: theme.colors.warningText }]}
              onPress={() => onSuggestWebSearch?.(webSearchSuggestion!)}
            >
              <Text style={[styles.webSearchActionLabel, { color: theme.colors.warningText, fontSize: scaleFontSize(12, scale) }]}>Rechercher sur le web</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {statsLabel ? <Text testID="message-generation-stats" style={[styles.statsText, { color: theme.colors.textSubtle, fontSize: scaleFontSize(11, scale), lineHeight: scaleLineHeight(14, scale) }]}>{statsLabel}</Text> : null}
    </View>
  );
}

const PENDING_RESPONSE_FRAMES = ['·  ', '·· ', '···'];

const styles = StyleSheet.create({
  stack: {
    width: '100%',
  },
  userStack: {
    alignItems: 'flex-end',
  },
  userBubbleShell: {
    width: '100%',
    alignItems: 'flex-end',
  },
  assistantStack: {
    alignItems: 'stretch',
    gap: 10,
  },
  base: {
    borderRadius: 20,
    padding: 16,
    gap: 10,
  },
  userBubble: {
    maxWidth: '56%',
    alignSelf: 'flex-end',
    marginLeft: 'auto',
    borderWidth: 1,
  },
  assistantBubble: {
    width: '100%',
    borderWidth: 1,
    paddingBottom: 14,
  },
  followUpBubble: {
    width: '100%',
    borderWidth: 1,
  },
  followUpHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  followUpMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  assistantHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  assistantBadgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
    justifyContent: 'flex-end',
  },
  followUpLabel: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  role: {
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  userRole: {
    color: '#d6d6d6',
  },
  assistantRole: {
  },
  providerBadge: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 4,
  },
  providerBadgeText: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.2,
  },
  userContent: {
    fontSize: 15,
    lineHeight: 22,
  },
  pendingState: {
    gap: 6,
    paddingVertical: 4,
  },
  pendingTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  pendingTitle: {
    fontSize: 15,
    fontWeight: '700',
  },
  pendingGlyph: {
    fontSize: 16,
    fontWeight: '700',
    minWidth: 24,
  },
  pendingCaption: {
    fontSize: 13,
    lineHeight: 18,
  },
  queryOverviewBox: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    gap: 10,
  },
  actionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    paddingTop: 2,
  },
  webSearchActionButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  webSearchActionLabel: {
    fontSize: 12,
    fontWeight: '800',
  },
  deleteActionButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  deleteActionLabel: {
    fontSize: 12,
    fontWeight: '800',
  },
  statsText: {
    fontSize: 11,
    lineHeight: 14,
    paddingHorizontal: 4,
  },
});

function isRenderableQueryOverview(message: ChatMessage) {
  const queryOverview = message.queryOverview;
  if (!queryOverview) {
    return false;
  }

  return Boolean(
    queryOverview.summary?.trim() ||
      queryOverview.searchQuery?.trim() ||
      queryOverview.sources?.length ||
      (message.provenance === 'web' && message.content.trim()),
  );
}

function buildDdgMarkdown(message: ChatMessage): string {
  if (message.provenance === 'web' && message.content.trim()) {
    return sanitizeDdgMarkdown(message.content);
  }

  if (!message.queryOverview) {
    return '';
  }

  const lines: string[] = ['# Vue d\'ensemble DDG', ''];
  const summary = sanitizeDdgMarkdown(message.queryOverview.summary?.trim() ?? '');
  if (summary) {
    lines.push(summary, '');
  }

  if (message.queryOverview.searchQuery?.trim()) {
    lines.push(`**Requête DDG :** \`${message.queryOverview.searchQuery.trim()}\``, '');
  }

  if (message.queryOverview.sources?.length) {
    lines.push('## Sources', '');
    for (const source of message.queryOverview.sources) {
      lines.push(`- [${source.title || source.href}](${source.href})`);
    }
    lines.push('');
  }

  return sanitizeDdgMarkdown(lines.join('\n').trim());
}

function sanitizeDdgMarkdown(markdown: string): string {
  const normalizedLines: string[] = [];

  for (const rawLine of markdown.replace(/\r\n/g, '\n').split('\n')) {
    const trimmed = rawLine.trim();
    if (/^(?:[-*]|•)\s*$/.test(trimmed)) {
      continue;
    }

    const heading = extractBulletHeading(trimmed);
    if (heading) {
      normalizedLines.push(`## ${heading}`, '');
      continue;
    }

    normalizedLines.push(rawLine);
  }

  return normalizedLines
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function containsMermaidFence(markdown: string): boolean {
  return /```mermaid\s*\n/i.test(markdown);
}

function extractBulletHeading(line: string): string | null {
  if (!/^(?:[-*]|•)\s+/.test(line)) {
    return null;
  }

  let candidate = line.replace(/^(?:[-*]|•)\s+/, '').trim();
  const boldWrapped = candidate.match(/^(?:\*\*|__)(.+?)(?:\*\*|__)$/);
  if (boldWrapped?.[1]) {
    candidate = boldWrapped[1].trim();
  }

  if (!candidate.endsWith(':')) {
    return null;
  }

  const heading = candidate.slice(0, -1).trim();
  if (!heading || /[.!?]$/.test(heading)) {
    return null;
  }

  return heading;
}

function formatGenerationStats(stats?: ChatMessage['stats']): string | null {
  if (!stats) {
    return null;
  }

  const tokens = Number.isFinite(stats.tokens) ? Math.max(0, Math.round(stats.tokens)) : 0;
  const tps = Number.isFinite(stats.tps) ? stats.tps : 0;
  return `${tokens} tokens · ${formatRate(tps)} tok/s`;
}

function formatRate(value: number): string {
  if (!Number.isFinite(value)) {
    return '0';
  }

  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function formatProviderLabel(value?: string): string | null {
  const normalized = value?.trim();
  return normalized ? `via ${normalized}` : null;
}

function formatProvenanceLabel(value?: ChatMessage['provenance']): string | null {
  switch (value) {
    case 'vault':
      return 'coffre';
    case 'web':
      return 'web';
    case 'hybrid':
      return 'web + coffre';
    default:
      return null;
  }
}
