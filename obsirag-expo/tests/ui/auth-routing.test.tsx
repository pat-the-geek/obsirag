import React from 'react';
import renderer from 'react-test-renderer';

const mockUseSegments = jest.fn();
const mockUseServerConfig = jest.fn();
const mockUseSessionStatus = jest.fn();
const mockUseSystemStatus = jest.fn();
const mockUseStoreHydrated = jest.fn();
const mockUseAppStore = jest.fn();

jest.mock('expo-router', () => ({
  Redirect: ({ href }: { href: string }) => {
    const ReactLocal = require('react');
    const { Text } = require('react-native');
    return ReactLocal.createElement(Text, { testID: 'redirect' }, href);
  },
  Stack: () => {
    const ReactLocal = require('react');
    const { Text } = require('react-native');
    return ReactLocal.createElement(Text, { testID: 'stack' }, 'stack');
  },
  Tabs: ({ children }: { children: React.ReactNode }) => {
    const ReactLocal = require('react');
    const { View } = require('react-native');
    return ReactLocal.createElement(View, { testID: 'tabs' }, children);
  },
  useSegments: () => mockUseSegments(),
  useRouter: () => ({ replace: jest.fn() }),
}));

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => mockUseServerConfig(),
  useSessionStatus: () => mockUseSessionStatus(),
}));

jest.mock('../../features/system/use-system-status', () => ({
  useSystemStatus: () => mockUseSystemStatus(),
}));

jest.mock('../../store/app-store', () => ({
  useStoreHydrated: () => mockUseStoreHydrated(),
  useAppStore: (selector: (state: { setActiveConversationId: (value?: string) => void }) => unknown) =>
    selector({ setActiveConversationId: mockUseAppStore }),
}));

import AuthLayout from '../../app/(auth)/_layout';
import IndexRoute from '../../app/index';
import TabsLayout from '../../app/(tabs)/_layout';

describe('auth routing guards', () => {
  beforeEach(() => {
    mockUseSegments.mockReturnValue(['(auth)', 'server-config']);
    mockUseServerConfig.mockReturnValue({ backendUrl: 'http://localhost:8000', useMockServer: false });
    mockUseSessionStatus.mockReturnValue({ isLoading: false, isError: true, data: undefined });
    mockUseSystemStatus.mockReturnValue({ isLoading: false, data: { startup: { ready: true } } });
    mockUseStoreHydrated.mockReturnValue(true);
    mockUseAppStore.mockReset();
  });

  it('does not redirect repeatedly when auth layout is already on server-config', () => {
    const tree = renderer.create(<AuthLayout />);

    expect(() => tree.root.findByProps({ testID: 'stack' })).not.toThrow();
    expect(() => tree.root.findByProps({ testID: 'redirect' })).toThrow();
  });

  it('redirects tabs session errors directly to server-config', () => {
    mockUseSegments.mockReturnValue(['(tabs)', 'index']);

    const tree = renderer.create(<TabsLayout />);

    expect(tree.root.findByProps({ testID: 'redirect' }).props.children).toBe('/(auth)/server-config');
  });

  it('redirects authenticated auth layout access to the main tabs shell', () => {
    mockUseSegments.mockReturnValue(['(auth)', 'login']);
    mockUseSessionStatus.mockReturnValue({ isLoading: false, isError: false, data: { authenticated: true } });

    const tree = renderer.create(<AuthLayout />);

    expect(tree.root.findByProps({ testID: 'redirect' }).props.children).toBe('/(tabs)');
  });

  it('redirects authenticated root access to the main tabs shell', () => {
    mockUseServerConfig.mockReturnValue({ backendUrl: 'http://localhost:8000', useMockServer: false });
    mockUseSessionStatus.mockReturnValue({ isLoading: false, isError: false, data: { authenticated: true } });
    mockUseStoreHydrated.mockReturnValue(true);

    const tree = renderer.create(<IndexRoute />);

    expect(tree.root.findByProps({ testID: 'redirect' }).props.children).toBe('/(tabs)');
  });
});