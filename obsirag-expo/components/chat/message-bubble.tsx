import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Pressable, StyleSheet, Text, View } from 'react-native';

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
  const isUser = message.role === 'user';
  const revealProgress = useRef(new Animated.Value(isUser || process.env.NODE_ENV === 'test' ? 1 : 0)).current;
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [entityContextsOpen, setEntityContextsOpen] = useState(false);
  const hasRenderableQueryOverview = isRenderableQueryOverview(message);
  const hasMermaidContent = containsMermaidFence(message.content);
  const shouldHideAssistantMainBubble = Boolean(
    !isUser && hasRenderableQueryOverview && !hasMermaidContent && (message.sentinel || message.provenance === 'web'),
  );
  const isPendingAssistant = Boolean(!isUser && (message.id === 'streaming-assistant' || message.id === 'pending-web-assistant'));
  const showWebSearchAction = Boolean(!isUser && !isPendingAssistant && webSearchSuggestion && onSuggestWebSearch);
  const showDeleteAction = Boolean(!isUser && !isPendingAssistant && onDeleteMessage);
  const ddgMarkdown = buildDdgMarkdown(message);
  const targetAssistantContent = shouldHideAssistantMainBubble ? ddgMarkdown : message.content;
  const statsLabel = !isUser && !isPendingAssistant ? formatGenerationStats(message.stats) : null;
  const [displayedAssistantContent, setDisplayedAssistantContent] = useState(
    isUser || process.env.NODE_ENV === 'test' ? targetAssistantContent : '',
  );
  const displayedAssistantContentRef = useRef(displayedAssistantContent);
  const [pendingFrameIndex, setPendingFrameIndex] = useState(0);

  useEffect(() => {
    displayedAssistantContentRef.current = displayedAssistantContent;
  }, [displayedAssistantContent]);

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
    if (isUser || process.env.NODE_ENV === 'test') {
      setDisplayedAssistantContent(targetAssistantContent);
      return undefined;
    }

    if (!targetAssistantContent) {
      setDisplayedAssistantContent('');
      return undefined;
    }

    const currentValue = displayedAssistantContentRef.current;
    const nextStart = targetAssistantContent.startsWith(currentValue) ? currentValue : '';
    if (nextStart !== currentValue) {
      setDisplayedAssistantContent(nextStart);
    }

    let visibleLength = nextStart.length;
    if (visibleLength >= targetAssistantContent.length) {
      setDisplayedAssistantContent(targetAssistantContent);
      return undefined;
    }

    const timer = setInterval(() => {
      const remaining = targetAssistantContent.length - visibleLength;
      const step = Math.max(1, Math.ceil(remaining / 12));
      visibleLength = Math.min(targetAssistantContent.length, visibleLength + step);
      setDisplayedAssistantContent(targetAssistantContent.slice(0, visibleLength));
      if (visibleLength >= targetAssistantContent.length) {
        clearInterval(timer);
      }
    }, 16);

    return () => clearInterval(timer);
  }, [isUser, targetAssistantContent]);

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
          <View style={[styles.base, isUser ? styles.userBubble : styles.assistantBubble]}>
            {isUser ? (
              <Text style={styles.userContent}>{renderEntityHighlightedText(message.content, 'dark', highlightEntities, undefined, `user-${message.id}`)}</Text>
            ) : isPendingAssistant && !displayedAssistantContent.trim() ? (
              <View testID="assistant-pending-state" style={styles.pendingState}>
                <View style={styles.pendingTitleRow}>
                  <Text style={styles.pendingTitle}>Réponse en préparation</Text>
                  <Text style={styles.pendingGlyph}>{PENDING_RESPONSE_FRAMES[pendingFrameIndex]}</Text>
                </View>
                <Text style={styles.pendingCaption}>{message.timeline?.[message.timeline.length - 1] ?? 'Traitement en cours'}</Text>
              </View>
            ) : (
              <MarkdownNote
                markdown={displayedAssistantContent}
                variant="article"
                tone="light"
                {...(highlightEntities ? { entityHighlights: highlightEntities } : {})}
                {...(onOpenNote ? { onOpenNote } : {})}
                {...(onOpenTag ? { onOpenTag } : {})}
              />
            )}
            {!isUser && message.sources?.length ? (
              <SourceList
                sources={message.sources}
                isOpen={sourcesOpen}
                onToggleOpen={() => setSourcesOpen((current) => !current)}
                onSelectSource={(source) => onOpenNote?.(source.filePath)}
              />
            ) : null}
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
      {!isUser && hasRenderableQueryOverview ? (
        <Animated.View style={assistantRevealStyle}>
          <View testID="message-query-overview-response" style={[styles.base, styles.followUpBubble]}>
            <View style={styles.followUpHeader}>
              <Text style={styles.assistantRole}>ObsiRAG</Text>
              <Text style={styles.followUpLabel}>Vue d'ensemble DDG</Text>
            </View>
            <View style={styles.queryOverviewBox}>
              <MarkdownNote
                markdown={displayedAssistantContent}
                tone="light"
                {...(highlightEntities ? { entityHighlights: highlightEntities } : {})}
                {...(onOpenNote ? { onOpenNote } : {})}
                {...(onOpenTag ? { onOpenTag } : {})}
              />
            </View>
          </View>
        </Animated.View>
      ) : null}
      {showWebSearchAction || showDeleteAction ? (
        <View style={styles.actionRow}>
          {showDeleteAction ? (
            <Pressable
              testID="message-delete-action"
              style={styles.deleteActionButton}
              onPress={() => onDeleteMessage?.(message.id)}
            >
              <Text style={styles.deleteActionLabel}>Supprimer la réponse</Text>
            </Pressable>
          ) : null}
          {showWebSearchAction ? (
            <Pressable
              testID="message-web-search-action"
              style={styles.webSearchActionButton}
              onPress={() => onSuggestWebSearch?.(webSearchSuggestion!)}
            >
              <Text style={styles.webSearchActionLabel}>Rechercher sur le web</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      {statsLabel ? <Text testID="message-generation-stats" style={styles.statsText}>{statsLabel}</Text> : null}
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
    backgroundColor: '#191919',
    borderWidth: 1,
    borderColor: '#2d2d2d',
  },
  assistantBubble: {
    width: '100%',
    backgroundColor: '#f4f1ea',
    borderWidth: 1,
    borderColor: '#ddd4c8',
    paddingBottom: 14,
  },
  followUpBubble: {
    width: '100%',
    backgroundColor: '#f4f1ea',
    borderWidth: 1,
    borderColor: '#ddd4c8',
  },
  followUpHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  followUpLabel: {
    color: '#5d4b38',
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
    color: '#2f2419',
  },
  userContent: {
    color: '#f1f1f1',
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
    color: '#2f2419',
    fontSize: 15,
    fontWeight: '700',
  },
  pendingGlyph: {
    color: '#7f6b55',
    fontSize: 16,
    fontWeight: '700',
    minWidth: 24,
  },
  pendingCaption: {
    color: '#6f5d49',
    fontSize: 13,
    lineHeight: 18,
  },
  queryOverviewBox: {
    borderRadius: 12,
    backgroundColor: '#fbf8f3',
    borderWidth: 1,
    borderColor: '#ded5c9',
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
    backgroundColor: '#efe3cf',
    borderWidth: 1,
    borderColor: '#dbc4a6',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  webSearchActionLabel: {
    color: '#5b3a0f',
    fontSize: 12,
    fontWeight: '800',
  },
  deleteActionButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#f6e3de',
    borderWidth: 1,
    borderColor: '#ddb6ab',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  deleteActionLabel: {
    color: '#7a2f22',
    fontSize: 12,
    fontWeight: '800',
  },
  statsText: {
    color: '#8b7864',
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
