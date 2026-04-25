import { ChatMessage } from '../../types/domain';

const STREAMING_ASSISTANT_ID = 'streaming-assistant';
const PENDING_WEB_ASSISTANT_ID = 'pending-web-assistant';

export function isLocalOnlyMessageForDeletion(message: ChatMessage | undefined): boolean {
  if (!message) {
    return false;
  }

  if (message.id === STREAMING_ASSISTANT_ID || message.id === PENDING_WEB_ASSISTANT_ID) {
    return true;
  }

  if (message.id.startsWith('web-user-')) {
    return true;
  }

  if (message.id.startsWith('web-') && message.provenance === 'web') {
    return true;
  }

  return Boolean(message.transient);
}
