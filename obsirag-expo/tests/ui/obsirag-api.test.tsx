import { ObsiRagApi } from '../../services/api/obsirag-api';
import { ChatMessage } from '../../types/domain';
import { NativeModules } from 'react-native';

describe('ObsiRagApi.streamConversationResponse', () => {
  const initialFetch = global.fetch;

  const fallbackMessage: ChatMessage = {
    id: 'assistant-1',
    role: 'assistant',
    content: 'Reponse fallback',
    createdAt: '2026-04-17T10:00:00Z',
    provenance: 'vault',
  };

  beforeEach(() => {
    global.fetch = jest.fn();
    NativeModules.SourceCode = undefined;
  });

  afterAll(() => {
    global.fetch = initialFetch;
  });

  it('rewrites localhost backend URLs to the Expo host on mobile', async () => {
    const api = new ObsiRagApi({
      backendUrl: 'http://localhost:8000',
      useMockServer: false,
    });

    NativeModules.SourceCode = {
      scriptURL: 'http://192.168.1.217:8081/index.bundle?platform=ios',
    };

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok' }),
    } as Response);

    await api.getHealth();

    expect(global.fetch).toHaveBeenCalledWith(
      'http://192.168.1.217:8000/api/v1/health',
      expect.any(Object),
    );
  });

  it('falls back to the non-streaming endpoint when the streaming fetch fails with Load failed', async () => {
    const api = new ObsiRagApi({
      backendUrl: 'http://localhost:8000',
      useMockServer: false,
    });
    const onComplete = jest.fn();

    (global.fetch as jest.Mock)
      .mockRejectedValueOnce(new Error('Load failed'))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => fallbackMessage,
      } as Response);

    const result = await api.streamConversationResponse('conv-1', 'bonjour', { onComplete });

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch).toHaveBeenNthCalledWith(
      1,
      'http://localhost:8000/api/v1/conversations/conv-1/messages/stream',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(global.fetch).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/v1/conversations/conv-1/messages',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(onComplete).toHaveBeenCalledWith(fallbackMessage);
    expect(result).toEqual(fallbackMessage);
  });

  it('falls back to the non-streaming endpoint when the stream reader fails before receiving bytes', async () => {
    const api = new ObsiRagApi({
      backendUrl: 'http://localhost:8000',
      useMockServer: false,
    });
    const onComplete = jest.fn();

    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: true,
        body: {
          getReader: () => ({
            read: async () => {
              throw new Error('Load failed');
            },
          }),
        },
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => fallbackMessage,
      } as Response);

    const result = await api.streamConversationResponse('conv-1', 'bonjour', { onComplete });

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(onComplete).toHaveBeenCalledWith(fallbackMessage);
    expect(result).toEqual(fallbackMessage);
  });
});