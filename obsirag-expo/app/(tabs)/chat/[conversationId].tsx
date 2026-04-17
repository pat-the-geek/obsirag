import { useMemo, useState } from 'react';
import { ActivityIndicator, Alert, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { MessageBubble } from '../../../components/chat/message-bubble';
import { MessageComposer } from '../../../components/chat/message-composer';
import { SourceList } from '../../../components/chat/source-list';
import { WebSearchPrompt } from '../../../components/chat/web-search-prompt';
import { Screen } from '../../../components/ui/screen';
import { useConversation, useExplicitWebSearch, useSaveConversation, useStreamMessage } from '../../../features/chat/use-chat';
import { useAppStore } from '../../../store/app-store';

export default function ConversationDetailScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ conversationId: string }>();
  const conversationId = useMemo(
    () => (Array.isArray(params.conversationId) ? params.conversationId[0] : params.conversationId),
    [params.conversationId],
  );
  const draft = useAppStore((state) => (conversationId ? state.drafts[conversationId] ?? '' : ''));
  const setDraft = useAppStore((state) => state.setDraft);
  const { data, isLoading, isRefetching, refetch } = useConversation(conversationId);
  const streamMessage = useStreamMessage(conversationId ?? '');
  const saveConversation = useSaveConversation();
  const explicitWebSearch = useExplicitWebSearch(conversationId ?? '');
  const [webSearchDraft, setWebSearchDraft] = useState('');

  function triggerExplicitWebSearch(query: string) {
    explicitWebSearch.mutate(query, {
      onSuccess: () => setWebSearchDraft(''),
      onError: (error) => Alert.alert('Recherche web impossible', error instanceof Error ? error.message : 'Erreur inconnue'),
    });
  }

  if (!conversationId || isLoading || !data) {
    return (
      <Screen backgroundColor="#1f1f1f">
        <ActivityIndicator />
      </Screen>
    );
  }

  return (
    <Screen scroll={false} refreshing={isRefetching} onRefresh={refetch} backgroundColor="#1f1f1f" contentStyle={styles.screenContent}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={Math.max(12, insets.bottom)} style={styles.keyboardShell}>
      <View style={[styles.shell, { paddingBottom: Math.max(14, insets.bottom + 8) }]}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.headerTitle}>{data.title}</Text>
            <Text style={styles.headerSubtitle}>Conversation centree, reponses developpees et actions contextuelles en bas d'ecran.</Text>
          </View>
          <View style={styles.actionsRow}>
            <Pressable
              style={styles.secondaryButton}
              onPress={() => {
                if (!conversationId) {
                  return;
                }
                saveConversation.mutate(conversationId, {
                  onSuccess: (result) => Alert.alert('Conversation sauvegardee', result.path),
                  onError: (error) => Alert.alert('Sauvegarde impossible', error instanceof Error ? error.message : 'Erreur inconnue'),
                });
              }}
            >
              <Text style={styles.secondaryButtonText}>Sauvegarder</Text>
            </Pressable>
            <Pressable
              style={styles.secondaryButton}
              onPress={() => {
                const fallbackQuery = draft.trim() || [...data.messages].reverse().find((item) => item.role === 'user')?.content?.trim() || '';
                if (!fallbackQuery) {
                  Alert.alert('Recherche web', 'Aucune requete disponible pour lancer la recherche web explicite.');
                  return;
                }
                triggerExplicitWebSearch(fallbackQuery);
              }}
            >
              <Text style={styles.secondaryButtonText}>Recherche web</Text>
            </Pressable>
          </View>
        </View>

        <ScrollView style={styles.thread} contentContainerStyle={[styles.threadContent, { paddingBottom: 28 + insets.bottom }]} keyboardShouldPersistTaps="handled">
          {data.messages.map((message, index) => {
            const previousUserQuery = [...data.messages.slice(0, index)].reverse().find((item) => item.role === 'user')?.content;

            return (
              <MessageBubble
                key={message.id}
                message={message}
                onOpenNote={(notePath) => router.push(`/(tabs)/note/${encodeURIComponent(notePath)}`)}
                onOpenPrimarySource={(notePath) => router.push(`/(tabs)/note/${encodeURIComponent(notePath)}`)}
                onSuggestWebSearch={(query) => setWebSearchDraft(query)}
                onUseQueryInChat={(query) => {
                  setDraft(conversationId, query);
                  setWebSearchDraft('');
                }}
                onReusePrompt={(query) => setDraft(conversationId, query)}
                {...(previousUserQuery ? { replyPrompt: previousUserQuery } : {})}
                {...(previousUserQuery ? { webSearchSuggestion: previousUserQuery } : {})}
              />
            );
          })}
        </ScrollView>

        <View style={styles.dock}>
          {webSearchDraft ? (
            <WebSearchPrompt
              value={webSearchDraft}
              onChangeText={setWebSearchDraft}
              onSubmit={() => triggerExplicitWebSearch(webSearchDraft.trim())}
              onUseInChat={() => {
                setDraft(conversationId, webSearchDraft.trim());
                setWebSearchDraft('');
              }}
              disabled={explicitWebSearch.isPending}
            />
          ) : null}

          <SourceList
            sources={data.messages[data.messages.length - 1]?.sources ?? []}
            onSelectSource={(source) => router.push(`/(tabs)/note/${encodeURIComponent(source.filePath)}`)}
          />

          {streamMessage.isPending ? <Text style={styles.statusText}>Generation en cours...</Text> : null}
          {explicitWebSearch.isPending ? <Text style={styles.statusText}>Recherche web en cours...</Text> : null}
          {streamMessage.error ? (
            <Text style={styles.errorText}>
              Erreur: {streamMessage.error instanceof Error ? streamMessage.error.message : 'generation indisponible'}
            </Text>
          ) : null}

          <MessageComposer
            value={draft}
            onChangeText={(value) => setDraft(conversationId, value)}
            onSubmit={() => streamMessage.mutate(draft.trim())}
            disabled={streamMessage.isPending || !draft.trim()}
          />
        </View>
      </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  keyboardShell: {
    flex: 1,
  },
  screenContent: {
    paddingHorizontal: 0,
    paddingTop: 0,
    gap: 0,
  },
  shell: {
    flex: 1,
    width: '100%',
    maxWidth: 880,
    alignSelf: 'center',
    paddingHorizontal: 18,
    paddingTop: 18,
    paddingBottom: 14,
    gap: 14,
  },
  header: {
    gap: 12,
  },
  headerCopy: {
    gap: 6,
  },
  headerTitle: {
    color: '#f3f3f3',
    fontSize: 22,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#9d9d9d',
    lineHeight: 20,
  },
  actionsRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    gap: 8,
  },
  secondaryButton: {
    borderRadius: 999,
    backgroundColor: '#2a2a2a',
    borderWidth: 1,
    borderColor: '#373737',
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: '#ededed',
    fontWeight: '700',
  },
  thread: {
    flex: 1,
  },
  threadContent: {
    paddingTop: 12,
    paddingBottom: 18,
    gap: 18,
  },
  dock: {
    gap: 10,
    paddingTop: 8,
    backgroundColor: '#1f1f1f',
  },
  statusText: {
    color: '#9f9f9f',
    fontSize: 13,
  },
  errorText: {
    color: '#f0b36a',
    fontSize: 13,
  },
});
