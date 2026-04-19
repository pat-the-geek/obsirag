Object.assign(globalThis, { __OBSIRAG_JEST__: true });

jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async () => null),
    setItem: jest.fn(async () => undefined),
    removeItem: jest.fn(async () => undefined),
    clear: jest.fn(async () => undefined),
  },
}));

jest.mock('react-native-webview', () => {
  const React = require('react');
  const { View } = require('react-native');

  function MockWebView(props: Record<string, unknown>) {
    return React.createElement(View, props);
  }

  return {
    WebView: MockWebView,
    default: MockWebView,
  };
});

jest.mock('react-native-svg', () => {
  const React = require('react');

  function createMock(name: string) {
    return React.forwardRef(function MockComponent(
      props: Record<string, unknown> & { children?: React.ReactNode },
      ref: React.ForwardedRef<unknown>,
    ) {
      return React.createElement(name, { ...props, ref }, props.children);
    });
  }

  return {
    __esModule: true,
    default: createMock('Svg'),
    Svg: createMock('Svg'),
    Circle: createMock('Circle'),
    G: createMock('G'),
    Line: createMock('Line'),
    Text: createMock('SvgText'),
  };
});

jest.mock('react-native-safe-area-context', () => {
  const React = require('react');

  return {
    SafeAreaProvider: ({ children }: { children?: React.ReactNode }) => children,
    SafeAreaView: ({ children }: { children?: React.ReactNode }) => children,
    useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
  };
});

jest.mock('d3-force', () => {
  const createChainableForce = () => {
    const force = {
      strength: () => force,
      distance: () => force,
      radius: () => force,
      iterations: () => force,
      id: () => force,
    };
    return force;
  };

  return {
    forceCenter: () => createChainableForce(),
    forceCollide: () => createChainableForce(),
    forceLink: () => createChainableForce(),
    forceManyBody: () => createChainableForce(),
    forceSimulation: (nodes: Array<Record<string, unknown>>) => {
      const simulation = {
        force: () => simulation,
        stop: () => simulation,
        tick: () => simulation,
        nodes: () => nodes,
      };
      return simulation;
    },
  };
});
