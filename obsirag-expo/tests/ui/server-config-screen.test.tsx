import React from 'react';
import renderer, { act } from 'react-test-renderer';

const mockReplace = jest.fn();
const mockUseServerConfig = jest.fn();
const mockUseSessionStatus = jest.fn();
const mockInvalidateQueries = jest.fn();
const mockSaveAccessToken = jest.fn();
const mockUseLocalSearchParams = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ replace: mockReplace }),
  useLocalSearchParams: () => mockUseLocalSearchParams(),
}));

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
}));

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => mockUseServerConfig(),
  useSessionStatus: () => mockUseSessionStatus(),
}));

jest.mock('../../services/storage/secure-session', () => ({
  saveAccessToken: (...args: unknown[]) => mockSaveAccessToken(...args),
}));

import ServerConfigScreen from '../../app/(auth)/server-config';

describe('server-config screen', () => {
  beforeEach(() => {
    mockReplace.mockReset();
    mockInvalidateQueries.mockReset();
    mockSaveAccessToken.mockReset();
    mockUseLocalSearchParams.mockReturnValue({});
    mockUseServerConfig.mockReturnValue({
      api: { createSession: jest.fn() },
      backendUrl: 'http://127.0.0.1:8000',
      accessToken: '',
      useMockServer: false,
      setBackendUrl: jest.fn(),
      setAccessToken: jest.fn(),
      setUseMockServer: jest.fn(),
    });
    mockUseSessionStatus.mockReturnValue({ isLoading: false, isError: false, data: { authenticated: true } });
  });

  it('auto-redirects to tabs when session is already valid on bootstrap', () => {
    act(() => {
      renderer.create(<ServerConfigScreen />);
    });

    expect(mockReplace).toHaveBeenCalledWith('/(tabs)');
  });

  it('stays on screen when opened intentionally from settings', () => {
    mockUseLocalSearchParams.mockReturnValue({ allowStay: '1' });

    act(() => {
      renderer.create(<ServerConfigScreen />);
    });

    expect(mockReplace).not.toHaveBeenCalled();
  });
});