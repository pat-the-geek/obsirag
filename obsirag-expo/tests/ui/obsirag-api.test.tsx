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
      } as unknown as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => fallbackMessage,
      } as Response);

    const result = await api.streamConversationResponse('conv-1', 'bonjour', { onComplete });

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(onComplete).toHaveBeenCalledWith(fallbackMessage);
    expect(result).toEqual(fallbackMessage);
  });

  it('falls back to the non-streaming endpoint when streaming returns a non-auth HTTP error', async () => {
    const api = new ObsiRagApi({
      backendUrl: 'http://localhost:8000',
      useMockServer: false,
    });
    const onComplete = jest.fn();

    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: async () => ({ detail: 'Bad gateway' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => fallbackMessage,
      } as Response);

    const result = await api.streamConversationResponse('conv-1', 'bonjour', { onComplete });

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch).toHaveBeenNthCalledWith(
      2,
      'http://localhost:8000/api/v1/conversations/conv-1/messages',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(onComplete).toHaveBeenCalledWith(fallbackMessage);
    expect(result).toEqual(fallbackMessage);
  });

  it('normalizes the backend English stream error message when fallback also fails', async () => {
    const api = new ObsiRagApi({
      backendUrl: 'http://localhost:8000',
      useMockServer: false,
    });

    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: async () => ({ detail: 'Unable to stream conversation response.' }),
      } as Response)
      .mockRejectedValueOnce(new Error('Load failed'));

    await expect(api.streamConversationResponse('conv-1', 'bonjour', {})).rejects.toThrow(
      'Impossible de diffuser la reponse de conversation.',
    );
  });

  it('returns the completion payload even when token frames were emitted before it', async () => {
    const api = new ObsiRagApi({
      backendUrl: 'http://localhost:8000',
      useMockServer: false,
    });
    const onToken = jest.fn();
    const onComplete = jest.fn();
    const frames = [
      'event: retrieval_status\ndata: {"message":"Génération locale"}\n\n',
      'event: token\ndata: {"token":"Bonjour "}\n\n',
      'event: token\ndata: {"token":"monde"}\n\n',
      'event: message_complete\ndata: {"id":"assistant-2","role":"assistant","content":"Bonjour monde","createdAt":"2026-04-18T12:00:00Z","provenance":"vault","timeline":["Génération locale"]}\n\n',
    ].join('');

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      body: {
        getReader: () => {
          let consumed = false;
          return {
            read: async () => {
              if (consumed) {
                return { done: true, value: undefined };
              }
              consumed = true;
              return { done: false, value: new TextEncoder().encode(frames) };
            },
          };
        },
      },
    } as unknown as Response);

    const result = await api.streamConversationResponse('conv-1', 'bonjour', { onToken, onComplete });

    expect(onToken).toHaveBeenCalledTimes(2);
    expect(onComplete).toHaveBeenCalledWith(result);
    expect(result.content).toBe('Bonjour monde');
  });
});