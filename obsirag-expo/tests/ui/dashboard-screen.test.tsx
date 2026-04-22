import React from 'react';
import renderer from 'react-test-renderer';
import { Text } from 'react-native';

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
          euriaProvider: 'Infomaniak',
          euriaModel: 'Qwen/Qwen3.5-122B-A10B-FP8',
          euriaEnabled: true,
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
    const textNodes = tree.root.findAllByType(Text);
    const renderedText = textNodes
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('LLM actif ObsiRAG');
    expect(renderedText).toContain('mlx-community/Qwen2.5-7B-Instruct-4bit');
    expect(renderedText).toContain('Euria Infomaniak');
    expect(renderedText).toContain('Qwen/Qwen3.5-122B-A10B-FP8');
    expect(renderedText).toContain('Provider: Infomaniak');
    expect(renderedText).toContain('Statut: Disponible');
    expect(renderedText).toContain('Source runtime: API FastAPI live');
    expect(renderedText).toContain('Backend: http://192.168.1.217:8000');
    expect(renderedText).toContain('React 19.1');
    expect(renderedText).toContain('Expo 54');
    expect(renderedText).toContain('ChromaDB');
    expect(renderedText).not.toContain('ChromaDB 1.5');
    expect(renderedText).toContain('Mode live');
    expect(renderedText).toContain('Indexation: Aucun traitement en cours');
    expect(renderedText).not.toContain('Indexation: Indexation terminée');
  });

  it('shows the current file only while indexing is running', () => {
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
          running: true,
          processed: 4,
          total: 12,
          current: 'Notes/En cours.md',
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
          euriaProvider: 'Infomaniak',
          euriaModel: 'Qwen/Qwen3.5-122B-A10B-FP8',
          euriaEnabled: true,
        },
      },
      isLoading: false,
      isRefetching: false,
      refetch: jest.fn(),
      isError: false,
      error: null,
    });

    const tree = renderer.create(<DashboardScreen />);
    const renderedText = tree.root
      .findAllByType(Text)
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('Indexation: Notes/En cours.md');
  });

  it('renders modified date and size for quick note results', () => {
    mockUseNoteSearch.mockReturnValue({
      data: [
        {
          title: 'Artemis II',
          filePath: 'Space/Artemis II.md',
          dateModified: '2026-04-19T14:35:00Z',
          sizeBytes: 4096,
        },
      ],
    });

    const tree = renderer.create(<DashboardScreen />);
    const renderedText = tree.root
      .findAllByType(Text)
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('Space/Artemis II.md');
    expect(renderedText).toContain('Modifie le');
    expect(renderedText).toContain('4 ko');
  });
});
