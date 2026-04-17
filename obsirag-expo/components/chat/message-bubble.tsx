import { Linking, Pressable, Share, StyleSheet, Text, View } from 'react-native';

import { ChatMessage } from '../../types/domain';
import { MarkdownNote } from '../notes/markdown-note';
import { StatusPill } from '../ui/status-pill';

type MessageBubbleProps = {
  message: ChatMessage;
  onOpenNote?: (notePath: string) => void;
  onSuggestWebSearch?: (query: string) => void;
  webSearchSuggestion?: string;
  onUseQueryInChat?: (query: string) => void;
  replyPrompt?: string;
  onReusePrompt?: (query: string) => void;
  onOpenPrimarySource?: (notePath: string) => void;
};

export function MessageBubble({
  message,
  onOpenNote,
  onSuggestWebSearch,
  webSearchSuggestion,
  onUseQueryInChat,
  replyPrompt,
  onReusePrompt,
  onOpenPrimarySource,
}: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const canTriggerWebSearch = Boolean(!isUser && message.sentinel && onSuggestWebSearch && webSearchSuggestion?.trim());
  const hasWebSources = Boolean(message.queryOverview?.sources.length);
  const reusableQuery = message.queryOverview?.searchQuery || message.queryOverview?.query || '';
  const canReusePrompt = Boolean(!isUser && replyPrompt?.trim() && onReusePrompt);
  const canOpenPrimarySource = Boolean(!isUser && message.primarySource?.filePath && onOpenPrimarySource);

  return (
    <View style={[styles.stack, isUser ? styles.userStack : styles.assistantStack]}>
      <View style={[styles.base, isUser ? styles.userBubble : styles.assistantBubble]}>
        <View style={styles.row}>
          <Text style={[styles.role, isUser ? styles.userRole : styles.assistantRole]}>{isUser ? 'Vous' : 'ObsiRAG'}</Text>
          {message.provenance ? <StatusPill label={message.provenance} tone="neutral" /> : null}
        </View>
        {isUser ? (
          <Text style={styles.userContent}>{message.content}</Text>
        ) : (
          <MarkdownNote markdown={message.content} variant="article" tone="dark" {...(onOpenNote ? { onOpenNote } : {})} />
        )}
        {message.queryOverview ? (
          <View style={styles.queryOverviewBox}>
            <Text style={styles.queryOverviewTitle}>Recherche web</Text>
            <Text style={styles.queryOverviewText}>{message.queryOverview.summary}</Text>
            <Text style={styles.queryLabel}>Requete: {message.queryOverview.searchQuery}</Text>
            {hasWebSources ? (
              <View style={styles.webSourceList}>
                {message.queryOverview?.sources.map((source, index) => (
                  <Pressable key={`${message.id}-web-source-${index}`} onPress={() => { void Linking.openURL(source.href); }} style={styles.webSourceCard}>
                    <Text style={styles.webSourceTitle}>{source.title}</Text>
                    {(source.domain || source.publishedAt) ? (
                      <Text style={styles.webSourceMeta}>
                        {[source.domain, source.publishedAt].filter(Boolean).join(' · ')}
                      </Text>
                    ) : null}
                    {source.body ? <Text style={styles.webSourceBody}>{source.body}</Text> : null}
                    <Text style={styles.webSourceHref}>{source.href}</Text>
                  </Pressable>
                ))}
              </View>
            ) : null}
            {onUseQueryInChat && reusableQuery ? (
              <Pressable style={styles.useQueryButton} onPress={() => onUseQueryInChat(reusableQuery)}>
                <Text style={styles.useQueryButtonText}>Utiliser cette requete dans le chat</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
        {message.timeline?.length ? (
          <View style={styles.timelineList}>
            {message.timeline.map((item, index) => (
              <Text key={`${message.id}-timeline-${index}`} style={styles.timelineItem}>
                {item}
              </Text>
            ))}
          </View>
        ) : null}
        {message.primarySource ? (
          <Text style={styles.source}>Note principale : {message.primarySource.noteTitle}</Text>
        ) : null}
        {message.sentinel ? <Text style={styles.sentinel}>Reponse de repli: aucune source suffisante dans le coffre.</Text> : null}
        {canTriggerWebSearch ? (
          <Pressable style={styles.webSearchButton} onPress={() => onSuggestWebSearch?.(webSearchSuggestion!.trim())}>
            <Text style={styles.webSearchButtonText}>Preparer une recherche web</Text>
          </Pressable>
        ) : null}
        {message.stats ? (
          <Text style={styles.meta}>
            {message.stats.tokens} tokens · TTFT {message.stats.ttft.toFixed(1)}s · {message.stats.tps.toFixed(0)} tok/s
          </Text>
        ) : null}
        {!isUser ? (
          <View style={styles.actionsBar}>
            {canReusePrompt ? (
              <Pressable style={styles.actionButton} onPress={() => onReusePrompt?.(replyPrompt!.trim())}>
                <Text style={styles.actionButtonText}>Relancer</Text>
              </Pressable>
            ) : null}
            <Pressable style={styles.actionButton} onPress={() => { void Share.share({ message: message.content }); }}>
              <Text style={styles.actionButtonText}>Partager</Text>
            </Pressable>
            {canOpenPrimarySource ? (
              <Pressable style={styles.actionButton} onPress={() => onOpenPrimarySource?.(message.primarySource!.filePath)}>
                <Text style={styles.actionButtonText}>Source</Text>
              </Pressable>
            ) : null}
            {canTriggerWebSearch ? (
              <Pressable style={styles.actionButton} onPress={() => onSuggestWebSearch?.(webSearchSuggestion!.trim())}>
                <Text style={styles.actionButtonText}>Web</Text>
              </Pressable>
            ) : null}
            {onUseQueryInChat && reusableQuery ? (
              <Pressable style={styles.actionButton} onPress={() => onUseQueryInChat(reusableQuery)}>
                <Text style={styles.actionButtonText}>Requete</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    width: '100%',
  },
  userStack: {
    alignItems: 'flex-end',
  },
  assistantStack: {
    alignItems: 'stretch',
  },
  base: {
    borderRadius: 20,
    padding: 16,
    gap: 10,
  },
  userBubble: {
    maxWidth: '56%',
    backgroundColor: '#191919',
    borderWidth: 1,
    borderColor: '#2d2d2d',
  },
  assistantBubble: {
    width: '100%',
    backgroundColor: '#202020',
    borderWidth: 1,
    borderColor: '#303030',
    paddingBottom: 14,
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
    color: '#f3f3f3',
  },
  userContent: {
    color: '#f1f1f1',
    fontSize: 15,
    lineHeight: 22,
  },
  source: {
    color: '#c9b18e',
    fontSize: 13,
    fontWeight: '600',
  },
  queryOverviewBox: {
    borderRadius: 12,
    backgroundColor: '#181818',
    borderWidth: 1,
    borderColor: '#343434',
    padding: 12,
    gap: 6,
  },
  queryOverviewTitle: {
    color: '#f1f1f1',
    fontWeight: '700',
  },
  queryOverviewText: {
    color: '#d0d0d0',
    lineHeight: 20,
  },
  queryLabel: {
    color: '#9c9c9c',
    fontSize: 12,
    fontWeight: '600',
  },
  webSourceList: {
    gap: 8,
  },
  webSourceCard: {
    borderRadius: 12,
    backgroundColor: '#222222',
    borderWidth: 1,
    borderColor: '#343434',
    padding: 10,
    gap: 4,
  },
  webSourceTitle: {
    color: '#f0f0f0',
    fontWeight: '700',
  },
  webSourceBody: {
    color: '#d0d0d0',
    lineHeight: 19,
  },
  webSourceMeta: {
    color: '#9f9f9f',
    fontSize: 12,
    fontWeight: '600',
  },
  webSourceHref: {
    color: '#9bc0ff',
    fontSize: 12,
    textDecorationLine: 'underline',
  },
  useQueryButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#4a4a4a',
    backgroundColor: '#292929',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  useQueryButtonText: {
    color: '#f3f3f3',
    fontWeight: '700',
  },
  timelineList: {
    gap: 4,
  },
  timelineItem: {
    color: '#a4a4a4',
    fontSize: 12,
  },
  sentinel: {
    color: '#f0b36a',
    fontSize: 12,
    fontWeight: '600',
  },
  webSearchButton: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    backgroundColor: '#f2f2f2',
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  webSearchButtonText: {
    color: '#171717',
    fontWeight: '700',
  },
  meta: {
    color: '#8f8f8f',
    fontSize: 12,
  },
  actionsBar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    paddingTop: 4,
    borderTopWidth: 1,
    borderTopColor: '#313131',
  },
  actionButton: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#3b3b3b',
    backgroundColor: '#252525',
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  actionButtonText: {
    color: '#d7d7d7',
    fontSize: 12,
    fontWeight: '700',
  },
});
