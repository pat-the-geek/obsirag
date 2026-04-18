import React from 'react';
import renderer from 'react-test-renderer';
import { Text } from 'react-native';

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockUseServerConfig = jest.fn();
const mockUseSessionStatus = jest.fn();
const mockUseSystemStatus = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush, replace: mockReplace }),
}));

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => mockUseServerConfig(),
  useSessionStatus: () => mockUseSessionStatus(),
}));

jest.mock('../../features/system/use-system-status', () => ({
  useSystemStatus: () => mockUseSystemStatus(),
}));

jest.mock('../../services/storage/secure-session', () => ({
  clearAccessToken: jest.fn(),
}));

import SettingsScreen from '../../app/(tabs)/settings';

describe('settings screen', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockReplace.mockReset();
    mockInvalidateQueries.mockReset();
    mockUseServerConfig.mockReturnValue({
      backendUrl: 'http://192.168.1.217:8000',
      useMockServer: false,
      accessToken: 'token-preview',
      setAccessToken: jest.fn(),
      setUseMockServer: jest.fn(),
    });
    mockUseSessionStatus.mockReturnValue({
      isRefetching: false,
      refetch: jest.fn(),
      data: {
        authenticated: true,
        requiresAuth: false,
        tokenPreview: 'tok_abc',
        mode: 'open',
      },
    });
    mockUseSystemStatus.mockReturnValue({
      isRefetching: false,
      refetch: jest.fn(),
      data: {
        llmAvailable: true,
        notesIndexed: 12,
        chunksIndexed: 48,
        autolearn: {
          running: true,
          managedBy: 'worker',
          pid: 4321,
          step: 'Veille active',
          startedAt: '2026-04-18T10:00:00Z',
          updatedAt: '2026-04-18T10:01:00Z',
          nextRunAt: '2026-04-18T11:00:00Z',
        },
        runtime: {
          llmProvider: 'MLX',
          llmModel: 'mlx-community/Qwen2.5-7B-Instruct-4bit',
          embeddingModel: 'paraphrase-multilingual-MiniLM-L12-v2',
        },
      },
    });
  });

  it('shows live runtime mode and active model details', () => {
    const tree = renderer.create(<SettingsScreen />);
    const textNodes = tree.root.findAllByType(Text);
    const renderedText = textNodes
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('Backend: http://192.168.1.217:8000');
    expect(renderedText).toContain('Source runtime: API FastAPI live');
    expect(renderedText).toContain('Modele actif: mlx-community/Qwen2.5-7B-Instruct-4bit');
    expect(renderedText).toContain('Provider LLM: MLX');
  });
});