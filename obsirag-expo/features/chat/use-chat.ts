import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';
import { useAppStore } from '../../store/app-store';
import { ChatMessage, ConversationDetail, SourceRef } from '../../types/domain';
import { removeMessageTurn } from './message-turns';

const STREAMING_ASSISTANT_ID = 'streaming-assistant';
const PENDING_WEB_ASSISTANT_ID = 'pending-web-assistant';
const WEB_SEARCH_PROGRESS_LABEL = 'Recherche sur le web en cours...';

function buildPendingAssistantMessage(id: string, provenance: ChatMessage['provenance'], timeline: string[], llmProvider?: string): ChatMessage {
  return {
    id,
    role: 'assistant',
    content: '',
    createdAt: new Date().toISOString(),
    transient: true,
    timeline,
    ...(llmProvider ? { llmProvider } : {}),
    ...(provenance ? { provenance } : {}),
  };
}

function appendTimelineStep(current: string[], next: string): string[] {
  if (!next.trim()) {
    return current;
  }
  if (current[current.length - 1] === next) {
    return current;
  }
  return [...current, next];
}

function isTransientExplicitWebMessage(message: ChatMessage): boolean {
  return Boolean(message.transient) || message.id === PENDING_WEB_ASSISTANT_ID || message.id.startsWith('web-user-') || (message.id.startsWith('web-') && message.provenance === 'web');
}

function isTransientStreamingMessage(message: ChatMessage, messages: ChatMessage[], index: number): boolean {
  if (message.id === STREAMING_ASSISTANT_ID) {
    return true;
  }

  return Boolean(message.transient) || (message.role === 'user' && messages[index + 1]?.id === STREAMING_ASSISTANT_ID);
}

function normalizeMessageContent(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function hasEquivalentRemoteMessage(remote: ConversationDetail, cachedMessage: ChatMessage): boolean {
  if (!cachedMessage.transient) {
    return remote.messages.some((message) => message.id === cachedMessage.id);
  }

  const normalizedContent = normalizeMessageContent(cachedMessage.content);
  return remote.messages.some((message) => {
    if (message.id === cachedMessage.id) {
      return true;
    }
    if (message.role !== cachedMessage.role) {
      return false;
    }
    return normalizeMessageContent(message.content) === normalizedContent;
  });
}

function findEquivalentMessageIndex(messages: ChatMessage[], candidate: ChatMessage): number {
  if (!candidate.transient) {
    return messages.findIndex((message) => message.id === candidate.id);
  }

  const normalizedContent = normalizeMessageContent(candidate.content);
  return messages.findIndex((message) => {
    if (message.id === candidate.id) {
      return true;
    }
    if (message.role !== candidate.role) {
      return false;
    }
    return normalizeMessageContent(message.content) === normalizedContent;
  });
}

function insertTransientMessageAtRelativePosition(mergedMessages: ChatMessage[], cachedMessages: ChatMessage[], cachedIndex: number, cachedMessage: ChatMessage): ChatMessage[] {
  const nextAnchoredIndex = cachedMessages.slice(cachedIndex + 1)
    .map((message, offset) => ({ message, index: cachedIndex + offset + 1 }))
    .find(({ message }) => findEquivalentMessageIndex(mergedMessages, message) >= 0);

  if (nextAnchoredIndex) {
    const insertionIndex = findEquivalentMessageIndex(mergedMessages, nextAnchoredIndex.message);
    if (insertionIndex >= 0) {
      return [
        ...mergedMessages.slice(0, insertionIndex),
        cachedMessage,
        ...mergedMessages.slice(insertionIndex),
      ];
    }
  }

  const previousAnchored = [...cachedMessages.slice(0, cachedIndex)].reverse().find((message) => findEquivalentMessageIndex(mergedMessages, message) >= 0);
  if (previousAnchored) {
    const previousIndex = findEquivalentMessageIndex(mergedMessages, previousAnchored);
    if (previousIndex >= 0) {
      return [
        ...mergedMessages.slice(0, previousIndex + 1),
        cachedMessage,
        ...mergedMessages.slice(previousIndex + 1),
      ];
    }
  }

  return [...mergedMessages, cachedMessage];
}

function upsertStreamingTurn(messages: ChatMessage[], userMessage: ChatMessage, assistantMessage: ChatMessage): ChatMessage[] {
  const stableMessages = messages.filter((item) => item.id !== userMessage.id && item.id !== STREAMING_ASSISTANT_ID);
  return [...stableMessages, userMessage, assistantMessage];
}

function mergeConversationWithTransientMessages(remote: ConversationDetail, cached?: ConversationDetail): ConversationDetail {
  if (!cached?.messages.length) {
    return remote;
  }

  let mergedMessages: ChatMessage[] = [...remote.messages];

  for (const [index, cachedMessage] of cached.messages.entries()) {
    if (hasEquivalentRemoteMessage(remote, cachedMessage)) {
      continue;
    }

    if (isTransientExplicitWebMessage(cachedMessage) || isTransientStreamingMessage(cachedMessage, cached.messages, index)) {
      mergedMessages = insertTransientMessageAtRelativePosition(mergedMessages, cached.messages, index, cachedMessage);
    }
  }

  return {
    ...remote,
    messages: mergedMessages,
    draft: cached.draft ?? remote.draft,
    ...(cached.lastGenerationStats ? { lastGenerationStats: cached.lastGenerationStats } : {}),
  };
}

export function useConversations() {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['conversations'],
    queryFn: () => api.getConversations(),
  });
}

export function useConversation(conversationId?: string) {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: async () => {
      const remoteConversation = await api.getConversation(conversationId as string);
      const cachedConversation = queryClient.getQueryData<ConversationDetail>(['conversation', conversationId]);
      return mergeConversationWithTransientMessages(remoteConversation, cachedConversation);
    },
    enabled: Boolean(conversationId),
  });
}

export function useCreateConversation() {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.createConversation(),
    onSuccess: async (conversation) => {
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      queryClient.setQueryData(['conversation', conversation.id], conversation);
    },
  });
}

export function useDeleteConversation() {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (conversationId: string) => api.deleteConversation(conversationId),
    onSuccess: async (_, conversationId) => {
      queryClient.removeQueries({ queryKey: ['conversation', conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

export function useSaveConversation() {
  const { api } = useServerConfig();

  return useMutation({
    mutationFn: (conversationId: string) => api.saveConversation(conversationId),
  });
}

export function useGenerateConversationReport() {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (conversationId: string) => api.generateConversationReport(conversationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['insights'] });
    },
  });
}

export function useDeleteConversationMessage(conversationId: string) {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (messageId: string) => {
      const current = queryClient.getQueryData<ConversationDetail>(['conversation', conversationId]);
      const targetMessage = current?.messages.find((message) => message.id === messageId);

      if (current && targetMessage?.provenance === 'web') {
        return {
          ...current,
          messages: removeMessageTurn(current.messages, messageId),
          updatedAt: new Date().toISOString(),
        };
      }

      return api.deleteConversationMessage(conversationId, messageId);
    },
    onSuccess: async (conversation) => {
      queryClient.setQueryData(['conversation', conversationId], conversation);
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

export function useExplicitWebSearch(conversationId: string) {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();
  const useEuriaForConversation = useAppStore((state) => state.useEuriaForConversation);

  return useMutation({
    mutationFn: async (query: string) => api.webSearch(query, { useEuria: useEuriaForConversation }),
    onMutate: async (query) => {
      const userMessage: ChatMessage = {
        id: `web-user-${Date.now()}`,
        role: 'user',
        content: `🌐 Recherche sur le web : ${query}`,
        createdAt: new Date().toISOString(),
        transient: true,
      };
      const pendingAssistant = buildPendingAssistantMessage(PENDING_WEB_ASSISTANT_ID, 'web', [
        'Réponse en préparation',
        WEB_SEARCH_PROGRESS_LABEL,
      ], useEuriaForConversation ? 'Euria' : 'MLX');

      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          messages: [...current.messages.filter((item) => item.id !== PENDING_WEB_ASSISTANT_ID), userMessage, pendingAssistant],
          updatedAt: new Date().toISOString(),
        };
      });

      return { userMessageId: userMessage.id, pendingAssistantId: pendingAssistant.id };
    },
    onSuccess: (result, _query, context) => {
      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        if (!current) {
          return current;
        }

        const assistantMessage: ChatMessage = {
          id: `web-${Date.now()}`,
          role: 'assistant',
          content: result.content,
          createdAt: new Date().toISOString(),
          ...(result.llmProvider ? { llmProvider: result.llmProvider } : {}),
          provenance: 'web',
          queryOverview: result.queryOverview,
          entityContexts: result.entityContexts,
          timeline: ['Réponse en préparation', WEB_SEARCH_PROGRESS_LABEL],
          ...(result.stats ? { stats: result.stats } : {}),
        };

        const baseMessages = current.messages.filter((item) => item.id !== PENDING_WEB_ASSISTANT_ID);
        const userMessage = context?.userMessageId ? baseMessages.find((item) => item.id === context.userMessageId) : undefined;
        const withoutAssistantReplacement = userMessage
          ? baseMessages.filter((item) => item.id !== userMessage.id)
          : baseMessages;

        return {
          ...current,
          messages: userMessage ? [...withoutAssistantReplacement, userMessage, assistantMessage] : [...baseMessages, assistantMessage],
          updatedAt: new Date().toISOString(),
        };
      });

      void queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
    onError: (_error, _query, context) => {
      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          messages: current.messages.filter((item) => item.id !== context?.userMessageId && item.id !== context?.pendingAssistantId),
        };
      });
    },
  });
}

export function useStreamMessage(conversationId: string) {
  const { api } = useServerConfig();
  const queryClient = useQueryClient();
  const setDraft = useAppStore((state) => state.setDraft);
  const useEuriaForConversation = useAppStore((state) => state.useEuriaForConversation);

  return useMutation({
    mutationFn: async (prompt: string) => {
      const conversation = queryClient.getQueryData<ConversationDetail>(['conversation', conversationId]);
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: prompt,
        createdAt: new Date().toISOString(),
        transient: true,
      };

      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        const safeCurrent = current ?? conversation;
        if (!safeCurrent) {
          return undefined;
        }
        const pendingAssistant = buildPendingAssistantMessage(STREAMING_ASSISTANT_ID, 'vault', ['Réponse en préparation'], useEuriaForConversation ? 'Euria' : 'MLX');
        return {
          ...safeCurrent,
          messages: upsertStreamingTurn(safeCurrent.messages, userMessage, pendingAssistant),
          draft: '',
          updatedAt: new Date().toISOString(),
        };
      });

      let streamedContent = '';
      let streamedTimeline: string[] = ['Réponse en préparation'];
      let streamedSources: NonNullable<ChatMessage['sources']> = [];
      let streamedPrimarySource: SourceRef | null = null;
      const message = await api.streamConversationResponse(conversationId, prompt, {
        onStatus: (status) => {
          streamedTimeline = appendTimelineStep(streamedTimeline, status);
          queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
            if (!current) {
              return current;
            }
            const draftAssistant: ChatMessage = {
              id: STREAMING_ASSISTANT_ID,
              role: 'assistant',
              content: streamedContent.trim(),
              createdAt: new Date().toISOString(),
              transient: true,
              provenance: 'vault',
              timeline: streamedTimeline,
              sources: streamedSources,
              primarySource: streamedPrimarySource,
            };
            return {
              ...current,
              messages: upsertStreamingTurn(current.messages, userMessage, draftAssistant),
            };
          });
        },
        onToken: (token) => {
          streamedContent += token;
          queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
            if (!current) {
              return current;
            }
            const draftAssistant: ChatMessage = {
              id: STREAMING_ASSISTANT_ID,
              role: 'assistant',
              content: streamedContent.trim(),
              createdAt: new Date().toISOString(),
              transient: true,
              provenance: 'vault',
              timeline: streamedTimeline,
              sources: streamedSources,
              primarySource: streamedPrimarySource,
            };
            return {
              ...current,
              messages: upsertStreamingTurn(current.messages, userMessage, draftAssistant),
            };
          });
        },
        onSources: ({ sources, primarySource }) => {
          streamedSources = sources ?? [];
          streamedPrimarySource = primarySource ?? null;
        },
        onComplete: (assistantMessage) => {
          queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
            if (!current) {
              return current;
            }
            const finalizedMessage: ChatMessage = {
              ...assistantMessage,
              transient: true,
              content: assistantMessage.content?.trim() ? assistantMessage.content : streamedContent.trim(),
              timeline: assistantMessage.timeline?.length ? assistantMessage.timeline : streamedTimeline,
              sources: assistantMessage.sources?.length ? assistantMessage.sources : streamedSources,
              primarySource: assistantMessage.primarySource ?? streamedPrimarySource,
            };
            return {
              ...current,
              messages: upsertStreamingTurn(current.messages, userMessage, finalizedMessage),
              ...(finalizedMessage.stats ? { lastGenerationStats: finalizedMessage.stats } : {}),
              updatedAt: new Date().toISOString(),
            };
          });
        },
      }, { useEuria: useEuriaForConversation });

      setDraft(conversationId, '');
      await queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
      await queryClient.invalidateQueries({ queryKey: ['conversations'] });
      return message;
    },
    onError: () => {
      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          messages: current.messages.filter((item) => item.id !== STREAMING_ASSISTANT_ID),
        };
      });
    },
  });
}
