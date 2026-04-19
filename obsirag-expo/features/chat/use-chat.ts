import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';
import { useAppStore } from '../../store/app-store';
import { ChatMessage, ConversationDetail, SourceRef } from '../../types/domain';
import { removeMessageTurn } from './message-turns';

const STREAMING_ASSISTANT_ID = 'streaming-assistant';
const PENDING_WEB_ASSISTANT_ID = 'pending-web-assistant';
const WEB_SEARCH_PROGRESS_LABEL = 'Recherche sur le web en cours...';

function buildPendingAssistantMessage(id: string, provenance: ChatMessage['provenance'], timeline: string[]): ChatMessage {
  return {
    id,
    role: 'assistant',
    content: '',
    createdAt: new Date().toISOString(),
    provenance,
    timeline,
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
  return message.id === PENDING_WEB_ASSISTANT_ID || message.id.startsWith('web-user-') || (message.id.startsWith('web-') && message.provenance === 'web');
}

function mergeConversationWithTransientMessages(remote: ConversationDetail, cached?: ConversationDetail): ConversationDetail {
  if (!cached?.messages.length) {
    return remote;
  }

  const remoteMessagesById = new Map(remote.messages.map((message) => [message.id, message]));
  const mergedMessages: ChatMessage[] = [];
  const consumedRemoteIds = new Set<string>();

  for (const cachedMessage of cached.messages) {
    const remoteMessage = remoteMessagesById.get(cachedMessage.id);
    if (remoteMessage) {
      mergedMessages.push(remoteMessage);
      consumedRemoteIds.add(remoteMessage.id);
      continue;
    }

    if (isTransientExplicitWebMessage(cachedMessage)) {
      mergedMessages.push(cachedMessage);
    }
  }

  for (const remoteMessage of remote.messages) {
    if (!consumedRemoteIds.has(remoteMessage.id)) {
      mergedMessages.push(remoteMessage);
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

  return useMutation({
    mutationFn: async (query: string) => api.webSearch(query),
    onMutate: async (query) => {
      const userMessage: ChatMessage = {
        id: `web-user-${Date.now()}`,
        role: 'user',
        content: `🌐 Recherche sur le web : ${query}`,
        createdAt: new Date().toISOString(),
      };
      const pendingAssistant = buildPendingAssistantMessage(PENDING_WEB_ASSISTANT_ID, 'web', [
        'Réponse en préparation',
        WEB_SEARCH_PROGRESS_LABEL,
      ]);

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
          provenance: 'web',
          stats: result.stats,
          queryOverview: result.queryOverview,
          entityContexts: result.entityContexts,
          timeline: ['Réponse en préparation', WEB_SEARCH_PROGRESS_LABEL],
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

  return useMutation({
    mutationFn: async (prompt: string) => {
      const conversation = queryClient.getQueryData<ConversationDetail>(['conversation', conversationId]);
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: prompt,
        createdAt: new Date().toISOString(),
      };

      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        const safeCurrent = current ?? conversation;
        if (!safeCurrent) {
          return undefined;
        }
        return {
          ...safeCurrent,
          messages: [
            ...safeCurrent.messages.filter((item) => item.id !== STREAMING_ASSISTANT_ID),
            userMessage,
            buildPendingAssistantMessage(STREAMING_ASSISTANT_ID, 'vault', ['Réponse en préparation']),
          ],
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
              provenance: 'vault',
              timeline: streamedTimeline,
              sources: streamedSources,
              primarySource: streamedPrimarySource,
            };
            const withoutDraft = current.messages.filter((item) => item.id !== STREAMING_ASSISTANT_ID);
            return {
              ...current,
              messages: [...withoutDraft, draftAssistant],
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
              provenance: 'vault',
              timeline: streamedTimeline,
              sources: streamedSources,
              primarySource: streamedPrimarySource,
            };
            const withoutDraft = current.messages.filter((item) => item.id !== STREAMING_ASSISTANT_ID);
            return {
              ...current,
              messages: [...withoutDraft, draftAssistant],
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
              content: assistantMessage.content?.trim() ? assistantMessage.content : streamedContent.trim(),
              timeline: assistantMessage.timeline?.length ? assistantMessage.timeline : streamedTimeline,
              sources: assistantMessage.sources?.length ? assistantMessage.sources : streamedSources,
              primarySource: assistantMessage.primarySource ?? streamedPrimarySource,
            };
            const withoutDraft = current.messages.filter((item) => item.id !== STREAMING_ASSISTANT_ID);
            return {
              ...current,
              messages: [...withoutDraft, finalizedMessage],
              ...(finalizedMessage.stats ? { lastGenerationStats: finalizedMessage.stats } : {}),
              updatedAt: new Date().toISOString(),
            };
          });
        },
      });

      setDraft(conversationId, '');
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
