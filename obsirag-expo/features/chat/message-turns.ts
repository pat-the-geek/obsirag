import { ChatMessage } from '../../types/domain';

export function removeMessageTurn(messages: ChatMessage[], messageId: string): ChatMessage[] {
  const targetIndex = messages.findIndex((message) => message.id === messageId);
  if (targetIndex === -1) {
    return messages;
  }

  const deletedIds = new Set<string>([messageId]);
  const targetMessage = messages[targetIndex];
  if (targetMessage.role === 'assistant' && targetIndex > 0) {
    const previousMessage = messages[targetIndex - 1];
    if (previousMessage.role === 'user') {
      deletedIds.add(previousMessage.id);
    }
  }

  return messages.filter((message) => !deletedIds.has(message.id));
}