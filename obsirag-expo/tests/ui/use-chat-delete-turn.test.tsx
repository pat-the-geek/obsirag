import { ChatMessage } from '../../types/domain';
import { removeMessageTurn } from '../../features/chat/message-turns';

describe('removeMessageTurn', () => {
  it('removes an assistant response and its preceding user question', () => {
    const messages: ChatMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Question 1',
        createdAt: '2026-04-17T12:00:00Z',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Réponse 1',
        createdAt: '2026-04-17T12:00:01Z',
        provenance: 'vault',
      },
      {
        id: 'user-2',
        role: 'user',
        content: 'Question 2',
        createdAt: '2026-04-17T12:00:02Z',
      },
      {
        id: 'assistant-2',
        role: 'assistant',
        content: 'Réponse 2',
        createdAt: '2026-04-17T12:00:03Z',
        provenance: 'vault',
      },
    ];

    expect(removeMessageTurn(messages, 'assistant-2').map((message) => message.id)).toEqual(['user-1', 'assistant-1']);
  });

  it('removes the explicit web-search user message together with its web response', () => {
    const messages: ChatMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Question 1',
        createdAt: '2026-04-17T12:00:00Z',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Réponse 1',
        createdAt: '2026-04-17T12:00:01Z',
        provenance: 'vault',
      },
      {
        id: 'web-user-1',
        role: 'user',
        content: '🌐 Recherche sur le web : Mermaid table features',
        createdAt: '2026-04-17T12:00:02Z',
      },
      {
        id: 'web-1',
        role: 'assistant',
        content: 'Résultat web',
        createdAt: '2026-04-17T12:00:03Z',
        provenance: 'web',
      },
    ];

    expect(removeMessageTurn(messages, 'web-1').map((message) => message.id)).toEqual(['user-1', 'assistant-1']);
  });

  it('leaves the list unchanged when the target message is unknown', () => {
    const messages: ChatMessage[] = [
      {
        id: 'user-1',
        role: 'user',
        content: 'Question 1',
        createdAt: '2026-04-17T12:00:00Z',
      },
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Réponse 1',
        createdAt: '2026-04-17T12:00:01Z',
        provenance: 'vault',
      },
    ];

    expect(removeMessageTurn(messages, 'missing').map((message) => message.id)).toEqual(['user-1', 'assistant-1']);
  });
});
