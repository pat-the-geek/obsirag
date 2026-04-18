import React from 'react';
import renderer from 'react-test-renderer';

const mockUseRouter = jest.fn();
const mockUseSystemStatus = jest.fn();
const mockUseNoteSearch = jest.fn();
const mockUseServerConfig = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => mockUseRouter(),
}));

jest.mock('../../features/system/use-system-status', () => ({
  useSystemStatus: (...args: unknown[]) => mockUseSystemStatus(...args),
}));

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => mockUseServerConfig(),
}));

jest.mock('../../features/notes/use-notes', () => ({
  useNoteSearch: (...args: unknown[]) => mockUseNoteSearch(...args),
}));

import DashboardScreen from '../../app/(tabs)/index';

describe('dashboard screen', () => {
  beforeEach(() => {
    mockUseRouter.mockReturnValue({ push: jest.fn() });
    mockUseNoteSearch.mockReturnValue({ data: [] });
    mockUseServerConfig.mockReturnValue({
      backendUrl: 'http://192.168.1.217:8000',
      useMockServer: false,
    });
    mockUseSystemStatus.mockReturnValue({
      data: {
        backendReachable: true,
        llmAvailable: true,
        notesIndexed: 12,
        chunksIndexed: 48,
        startup: {
          ready: true,
          steps: [],
          currentStep: 'Tous les services sont opérationnels',
        },
        indexing: {
          running: false,
          processed: 12,
          total: 12,
          current: 'Indexation terminée',
        },
        autolearn: {
          active: true,
          managedBy: 'worker',
          step: 'Veille active',
          log: [],
        },
        runtime: {
          llmProvider: 'MLX',
          llmModel: 'mlx-community/Qwen2.5-7B-Instruct-4bit',
          embeddingModel: 'paraphrase-multilingual-MiniLM-L12-v2',
          vectorStore: 'ChromaDB',
          nerModel: 'xx_ent_wiki_sm',
          autolearnMode: 'worker',
        },
      },
      isLoading: false,
      isRefetching: false,
      refetch: jest.fn(),
      isError: false,
      error: null,
    });
  });

  it('renders the active ObsiRAG LLM model returned by system status', () => {
    const tree = renderer.create(<DashboardScreen />);
    const textNodes = tree.root.findAllByType('Text');
    const renderedText = textNodes
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('LLM actif ObsiRAG');
    expect(renderedText).toContain('mlx-community/Qwen2.5-7B-Instruct-4bit');
    expect(renderedText).toContain('Source runtime: API FastAPI live');
    expect(renderedText).toContain('Backend: http://192.168.1.217:8000');
    expect(renderedText).toContain('Mode live');
  });
});
