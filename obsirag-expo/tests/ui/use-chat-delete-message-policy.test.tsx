import { ChatMessage } from '../../types/domain';
import { isLocalOnlyMessageForDeletion } from '../../features/chat/delete-message-policy';

describe('isLocalOnlyMessageForDeletion', () => {
  it('returns false for persisted assistant message from Euria with web provenance', () => {
    const message: ChatMessage = {
      id: '9f2f4f4c4fce4f57a3c53b5e2fbadb22',
      role: 'assistant',
      content: 'Reponse Euria issue du web',
      createdAt: '2026-04-25T10:00:00Z',
      provenance: 'web',
      transient: false,
    };

    expect(isLocalOnlyMessageForDeletion(message)).toBe(false);
  });

  it('returns true for explicit web assistant message created client-side', () => {
    const message: ChatMessage = {
      id: 'web-1714020000000',
      role: 'assistant',
      content: 'Resultat web explicite',
      createdAt: '2026-04-25T10:00:01Z',
      provenance: 'web',
    };

    expect(isLocalOnlyMessageForDeletion(message)).toBe(true);
  });

  it('returns true for explicit web user prompt message', () => {
    const message: ChatMessage = {
      id: 'web-user-1714020000001',
      role: 'user',
      content: 'Recherche web',
      createdAt: '2026-04-25T10:00:02Z',
    };

    expect(isLocalOnlyMessageForDeletion(message)).toBe(true);
  });

  it('returns true for transient messages', () => {
    const message: ChatMessage = {
      id: 'assistant-temp',
      role: 'assistant',
      content: 'Generation en cours',
      createdAt: '2026-04-25T10:00:03Z',
      transient: true,
    };

    expect(isLocalOnlyMessageForDeletion(message)).toBe(true);
  });
});
