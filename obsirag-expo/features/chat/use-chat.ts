import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useServerConfig } from '../auth/use-server-config';
import { useAppStore } from '../../store/app-store';
import { ChatMessage, ConversationDetail, SourceRef } from '../../types/domain';
import { removeMessageTurn } from './message-turns';

export function useConversations() {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['conversations'],
    queryFn: () => api.getConversations(),
  });
}

export function useConversation(conversationId?: string) {
  const { api } = useServerConfig();

  return useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.getConversation(conversationId as string),
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
        content: `🌐 Recherche web : ${query}`,
        createdAt: new Date().toISOString(),
      };

      queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
        if (!current) {
          return current;
        }

        return {
          ...current,
          messages: [...current.messages, userMessage],
          updatedAt: new Date().toISOString(),
        };
      });

      return { userMessageId: userMessage.id };
    },
    onSuccess: (result) => {
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
          queryOverview: result.queryOverview,
          entityContexts: result.entityContexts,
          timeline: ['Recherche web explicite'],
        };

        return {
          ...current,
          messages: [...current.messages, assistantMessage],
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
          messages: current.messages.filter((item) => item.id !== context?.userMessageId),
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
          messages: [...safeCurrent.messages, userMessage],
          draft: '',
          updatedAt: new Date().toISOString(),
        };
      });

      let streamedContent = '';
      let streamedTimeline: string[] = [];
      let streamedSources: NonNullable<ChatMessage['sources']> = [];
      let streamedPrimarySource: SourceRef | null = null;
      const message = await api.streamConversationResponse(conversationId, prompt, {
        onStatus: (status) => {
          streamedTimeline = [...streamedTimeline, status];
          queryClient.setQueryData<ConversationDetail | undefined>(['conversation', conversationId], (current) => {
            if (!current) {
              return current;
            }
            const draftAssistant: ChatMessage = {
              id: 'streaming-assistant',
              role: 'assistant',
              content: streamedContent.trim(),
              createdAt: new Date().toISOString(),
              provenance: 'vault',
              timeline: streamedTimeline,
              sources: streamedSources,
              primarySource: streamedPrimarySource,
            };
            const withoutDraft = current.messages.filter((item) => item.id !== 'streaming-assistant');
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
              id: 'streaming-assistant',
              role: 'assistant',
              content: streamedContent.trim(),
              createdAt: new Date().toISOString(),
              provenance: 'vault',
              timeline: streamedTimeline,
              sources: streamedSources,
              primarySource: streamedPrimarySource,
            };
            const withoutDraft = current.messages.filter((item) => item.id !== 'streaming-assistant');
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
            const withoutDraft = current.messages.filter((item) => item.id !== 'streaming-assistant');
            return {
              ...current,
              messages: [...withoutDraft, assistantMessage],
              ...(assistantMessage.stats ? { lastGenerationStats: assistantMessage.stats } : {}),
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
          messages: current.messages.filter((item) => item.id !== 'streaming-assistant'),
        };
      });
    },
  });
}
