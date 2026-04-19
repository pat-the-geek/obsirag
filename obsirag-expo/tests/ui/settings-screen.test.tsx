import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Pressable, Text } from 'react-native';

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockUseServerConfig = jest.fn();
const mockUseSessionStatus = jest.fn();
const mockUseSystemStatus = jest.fn();
const mockSetThemeMode = jest.fn();

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: {
    themeMode: 'system' | 'light' | 'dark' | 'quiet' | 'abyss';
    setThemeMode: typeof mockSetThemeMode;
  }) => unknown) =>
    selector({
      themeMode: 'system',
      setThemeMode: mockSetThemeMode,
    }),
}));

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
    mockSetThemeMode.mockReset();
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

  it('renders theme choices at the top and allows selecting Dark+', () => {
    const tree = renderer.create(<SettingsScreen />);
    const renderedText = tree.root
      .findAllByType(Text)
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('Affichage');
    expect(renderedText).toContain('Automatique');
    expect(renderedText).toContain('Light+');
    expect(renderedText).toContain('Dark+');
    expect(renderedText).toContain('Atelier');
    expect(renderedText).toContain('Noctis');

    const darkOption = tree.root.findAllByType(Pressable).find((node) =>
      node.findAllByType(Text).some((textNode) => textNode.props.children === 'Dark+'),
    );

    expect(darkOption).toBeTruthy();

    act(() => {
      darkOption?.props.onPress();
    });

    expect(mockSetThemeMode).toHaveBeenCalledWith('dark');
  });

  it('allows selecting the new Noctis theme', () => {
    const tree = renderer.create(<SettingsScreen />);

    const abyssOption = tree.root.findAllByType(Pressable).find((node) =>
      node.findAllByType(Text).some((textNode) => textNode.props.children === 'Noctis'),
    );

    expect(abyssOption).toBeTruthy();

    act(() => {
      abyssOption?.props.onPress();
    });

    expect(mockSetThemeMode).toHaveBeenCalledWith('abyss');
  });
});