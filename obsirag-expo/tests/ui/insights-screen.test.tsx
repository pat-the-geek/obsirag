import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { ScrollView, Text } from 'react-native';

jest.useFakeTimers();

const mockUseRouter = jest.fn();
const mockUseInsights = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => mockUseRouter(),
}));

jest.mock('../../features/insights/use-insights', () => ({
  useInsights: (...args: unknown[]) => mockUseInsights(...args),
}));

import InsightsScreen from '../../app/(tabs)/insights/index';
import { InsightListItem } from '../../components/insights/insight-list-item';
import { InsightItem } from '../../types/domain';

function buildInsight(index: number): InsightItem {
  return {
    id: `insight-${index}`,
    title: `Insight ${index}`,
    filePath: `obsirag/insights/insight-${index}.md`,
    kind: index % 2 === 0 ? 'insight' : 'synapse',
    tags: index % 3 === 0 ? ['tag-a'] : ['tag-b'],
    excerpt: `Extrait ${index}`,
  };
}

describe('InsightsScreen', () => {
  beforeEach(() => {
    mockUseRouter.mockReturnValue({ push: jest.fn() });
    mockUseInsights.mockReturnValue({
      data: Array.from({ length: 55 }, (_, index) => buildInsight(index + 1)),
      isLoading: false,
      isRefetching: false,
      refetch: jest.fn(),
    });
  });

  it('loads the insights progressively when reaching the bottom', () => {
    const tree = renderer.create(<InsightsScreen />);

    expect(tree.root.findAllByType(InsightListItem)).toHaveLength(12);

    const countBefore = tree.root.findByProps({ testID: 'insights-visible-count' });
    const countBeforeText = countBefore.findAllByType(Text).map((node) => String(Array.isArray(node.props.children) ? node.props.children.join('') : node.props.children ?? '')).join(' ');
    expect(countBeforeText).toContain('12 sur 55');

    act(() => {
      jest.advanceTimersByTime(150);
    });

    expect(tree.root.findAllByType(InsightListItem)).toHaveLength(24);

    act(() => {
      tree.root.findByType(ScrollView).props.onScroll({
        nativeEvent: {
          contentOffset: { x: 0, y: 1200 },
          contentSize: { width: 400, height: 1600 },
          layoutMeasurement: { width: 400, height: 300 },
        },
      });
    });

    expect(tree.root.findAllByType(InsightListItem)).toHaveLength(42);

    const countAfter = tree.root.findByProps({ testID: 'insights-visible-count' });
    const countAfterText = countAfter.findAllByType(Text).map((node) => String(Array.isArray(node.props.children) ? node.props.children.join('') : node.props.children ?? '')).join(' ');
    expect(countAfterText).toContain('42 sur 55');
  });
});