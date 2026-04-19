import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

const mockPush = jest.fn();
const mockDetectNoteSynapses = jest.fn();
const mockSetFocusedNode = jest.fn();
const mockGraphRefetch = jest.fn();
const mockSubgraphRefetch = jest.fn();
const mockInvalidateQueries = jest.fn();
let mockGraphSearchParams: { tag?: string } = {};

jest.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({
    invalidateQueries: mockInvalidateQueries,
  }),
}));

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useLocalSearchParams: () => mockGraphSearchParams,
  usePathname: () => '/graph',
}));

jest.mock('../../components/graph/knowledge-graph', () => ({
  KnowledgeGraph: ({ data, onSelectNode, zoom }: { data: { nodes: Array<{ id: string; label: string }> }; onSelectNode?: (value: string) => void; zoom: number }) => {
    const ReactLocal = require('react');
    const { Pressable: PressableLocal, Text: TextLocal, View: ViewLocal } = require('react-native');

    return ReactLocal.createElement(
      ViewLocal,
      null,
      ReactLocal.createElement(TextLocal, null, `${zoom.toFixed(1)} x`),
      ...data.nodes.map((node) =>
        ReactLocal.createElement(
          PressableLocal,
          { key: node.id, testID: `graph-node-${node.id}`, onPress: () => onSelectNode?.(node.id) },
          ReactLocal.createElement(TextLocal, null, node.label),
        ),
      ),
    );
  },
}));

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => ({
    api: {
      detectNoteSynapses: mockDetectNoteSynapses,
    },
    backendUrl: 'http://localhost:8000',
    useMockServer: false,
  }),
}));

jest.mock('../../features/graph/use-graph', () => ({
  useGraph: () => ({
    data: {
      nodes: [
        { id: 'note-1', label: 'Artemis II', group: 'Space', degree: 4, tags: ['mission', 'nasa'], noteType: 'user', dateModified: '2026-04-16T09:00:00Z' },
        { id: 'note-2', label: 'Artemis Program', group: 'Space', degree: 7, tags: ['program', 'nasa'], noteType: 'insight', dateModified: '2026-04-15T09:00:00Z' },
        { id: 'note-3', label: 'Apollo Legacy', group: 'History', degree: 2, tags: ['archive'], noteType: 'report', dateModified: '2026-03-20T09:00:00Z' },
        { id: 'note-4', label: 'Deep Space Network', group: 'Space', degree: 5, tags: ['nasa', 'network'], noteType: 'user', dateModified: '2026-04-14T09:00:00Z' },
        { id: 'note-5', label: 'Launch Logistics', group: 'Operations', degree: 3, tags: ['nasa', 'mission'], noteType: 'user', dateModified: '2026-04-13T09:00:00Z' },
      ],
      edges: [
        { id: 'edge-1', source: 'note-1', target: 'note-2' },
        { id: 'edge-2', source: 'note-2', target: 'note-3' },
      ],
      metrics: { nodeCount: 5, edgeCount: 2, density: 0.2, filteredNoteCount: 5, totalNoteCount: 5 },
      topNodes: [
        { id: 'note-2', label: 'Artemis Program', degree: 7 },
        { id: 'note-1', label: 'Artemis II', degree: 4 },
      ],
      filterOptions: {
        folders: ['History', 'Space', 'Operations', 'Alpha', 'Beta', 'Gamma', 'Delta', 'Epsilon', 'Zeta', 'Eta', 'Theta', 'Iota', 'Kappa', 'Lambda', 'Mu', 'Nu', 'Xi'],
        tags: ['archive', 'mission', 'nasa', 'program', 'network', 'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota', 'kappa', 'lambda', 'omega'],
        types: ['user', 'report', 'insight', 'synapse'],
      },
      noteOptions: [
        { title: 'Apollo Legacy', filePath: 'note-3', dateModified: '2026-03-20T09:00:00Z', noteType: 'report' },
        { title: 'Artemis II', filePath: 'note-1', dateModified: '2026-04-16T09:00:00Z', noteType: 'user' },
        { title: 'Artemis Program', filePath: 'note-2', dateModified: '2026-04-15T09:00:00Z', noteType: 'insight' },
      ],
      spotlight: [
        { filePath: 'note-2', title: 'Artemis Program', score: 1, dateModified: '2026-04-15', tags: ['program', 'nasa'], noteType: 'insight' },
      ],
      recentNotes: [
        { title: 'Artemis II', filePath: 'note-1', dateModified: '2026-04-16T09:00:00Z', noteType: 'user' },
      ],
      folderSummary: [{ label: 'Space', count: 2 }],
      tagSummary: [{ label: 'nasa', count: 2 }],
      typeSummary: [{ label: 'insight', count: 1 }],
      legend: [{ key: 'user', label: 'Note', color: '#60a5fa' }],
    },
    isLoading: false,
    isRefetching: false,
    refetch: mockGraphRefetch,
  }),
  useGraphSubgraph: (noteId?: string, _depth = 1, filters?: { tags?: string[]; noteTypes?: string[] }) => {
    if (!noteId) {
      return {
        data: undefined,
        isLoading: false,
        isRefetching: false,
        refetch: mockSubgraphRefetch,
      };
    }

    const baseNodes = [
      { id: noteId, label: 'Artemis Program', group: 'Space', degree: 7, tags: ['program', 'nasa'], noteType: 'insight', dateModified: '2026-04-15T09:00:00Z' },
      { id: 'note-3', label: 'Apollo Legacy', group: 'History', degree: 2, tags: ['archive'], noteType: 'report', dateModified: '2026-03-20T09:00:00Z' },
    ];
    const keptNodes = baseNodes.filter((node) => {
      if (filters?.tags?.[0] && !node.tags.includes(filters.tags[0])) {
        return false;
      }
      if (filters?.noteTypes?.[0] && node.noteType !== filters.noteTypes[0]) {
        return false;
      }
      return true;
    });
    const keptIds = new Set(keptNodes.map((node) => node.id));
    const keptEdges = [{ id: 'edge-2', source: noteId, target: 'note-3' }].filter((edge) => keptIds.has(edge.source) && keptIds.has(edge.target));

    return {
      data: {
        nodes: keptNodes,
        edges: keptEdges,
        metrics: {
          nodeCount: keptNodes.length,
          edgeCount: keptEdges.length,
          density: keptNodes.length > 1 ? 0.5 : 0,
          filteredNoteCount: keptNodes.length,
          totalNoteCount: 3,
        },
        topNodes: keptNodes.map((node) => ({ id: node.id, label: node.label, degree: node.degree })),
        filterOptions: {
          folders: ['History', 'Space'],
          tags: ['archive', 'program', 'nasa'],
          types: ['user', 'report', 'insight', 'synapse'],
        },
        noteOptions: [
          { title: 'Apollo Legacy', filePath: 'note-3', dateModified: '2026-03-20T09:00:00Z', noteType: 'report' },
          { title: 'Artemis Program', filePath: noteId, dateModified: '2026-04-15T09:00:00Z', noteType: 'insight' },
        ],
        spotlight: keptNodes.map((node) => ({ filePath: node.id, title: node.label, score: node.degree / 7, dateModified: '2026-04-15', tags: node.tags, noteType: node.noteType })),
        recentNotes: keptNodes.map((node) => ({ title: node.label, filePath: node.id, dateModified: node.dateModified, noteType: node.noteType })),
        folderSummary: [{ label: 'Space', count: keptNodes.filter((node) => node.group === 'Space').length }].filter((item) => item.count > 0),
        tagSummary: [{ label: 'archive', count: keptNodes.filter((node) => node.tags.includes('archive')).length }].filter((item) => item.count > 0),
        typeSummary: Array.from(new Set(keptNodes.map((node) => node.noteType))).map((type) => ({ label: type, count: keptNodes.filter((node) => node.noteType === type).length })),
        legend: [{ key: 'report', label: 'Rapport', color: '#f59e0b' }],
      },
      isLoading: false,
      isRefetching: false,
      refetch: mockSubgraphRefetch,
    };
  },
}));

import GraphScreen from '../../app/(tabs)/graph';

function findPressableByLabel(tree: renderer.ReactTestRenderer, label: string) {
  return tree.root.findAll((node) => {
    if (typeof node.props.onPress !== 'function') {
      return false;
    }
    const texts = node.findAllByType(Text).flatMap((textNode) => {
      const value = textNode.props.children;
      return Array.isArray(value) ? value : [value];
    });
    const normalized = texts
      .filter((value): value is string | number => typeof value === 'string' || typeof value === 'number')
      .map((value) => String(value))
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim();
    return normalized.includes(label);
  })[0];
}

describe('GraphScreen', () => {
  beforeEach(() => {
    mockGraphSearchParams = {};
    mockDetectNoteSynapses.mockReset();
    mockDetectNoteSynapses.mockResolvedValue({
      sourceNotePath: 'note-2',
      createdCount: 1,
      created: [{ title: 'Synapse mock', filePath: 'obsirag/synapses/mock/synapse-note.md' }],
      message: '1 synapse mock detectee pour cet element.',
    });
    mockPush.mockReset();
    mockGraphRefetch.mockReset();
    mockSubgraphRefetch.mockReset();
    mockSetFocusedNode.mockReset();
    mockInvalidateQueries.mockReset();
  });

  it('renders a visual graph and supports focus/open actions', () => {
    let tree!: renderer.ReactTestRenderer;
    act(() => {
      tree = renderer.create(<GraphScreen />);
    });

    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    });
    const joined = texts
      .filter((value): value is string | number => typeof value === 'string' || typeof value === 'number')
      .map((value) => String(value))
      .join(' ');

    expect(joined).toMatch(/Graphe de connaissances/);
    expect(joined).toMatch(/5\s+noeuds\s+·\s+2\s+aretes/);
    expect(joined).toMatch(/Touchez un noeud pour isoler son voisinage direct/);
    expect(joined).toMatch(/Tous les groupes/);
    expect(joined).toMatch(/Tous les tags/);
    expect(joined).toMatch(/Tous les types/);
    expect(joined).toMatch(/Toutes les dates/);
    expect(joined).toMatch(/1\.0\s*x/);
    expect(joined).toMatch(/Parcours par centralite/);
    expect(joined).toMatch(/Parcours recent/);
    expect(joined).toMatch(/Ouvrir une note/);
    expect(joined).toMatch(/notes affichees/);

    const svgNode = tree.root.find((node) => node.props.testID === 'graph-node-note-2');
    act(() => {
      svgNode.props.onPress();
    });

    expect(tree.root.findAllByType(Text).some((node) => node.props.children === 'Revenir a la vue d\'ensemble')).toBe(true);

    act(() => {
      findPressableByLabel(tree, 'Tous les tags')?.props.onPress();
    });

    const tagTexts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    }).filter((value): value is string | number => typeof value === 'string' || typeof value === 'number').map((value) => String(value));
    expect(tagTexts.some((value) => /^#nasa · \d+$/.test(value))).toBe(true);
    expect(tagTexts).not.toContain('#omega · 0');

    act(() => {
      findPressableByLabel(tree, 'Tous les groupes')?.props.onPress();
    });

    const groupTexts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    }).filter((value): value is string | number => typeof value === 'string' || typeof value === 'number').map((value) => String(value));
    expect(groupTexts.some((value) => /^Space · \d+$/.test(value))).toBe(true);
    expect(groupTexts.some((value) => /^History · \d+$/.test(value))).toBe(true);
    expect(groupTexts).not.toContain('Xi · 0');

    act(() => {
      findPressableByLabel(tree, 'Tous les types')?.props.onPress();
    });

    act(() => {
      findPressableByLabel(tree, 'Rapport')?.props.onPress();
    });

    act(() => {
      findPressableByLabel(tree, 'archive')?.props.onPress();
    });

    const filteredTexts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    }).filter((value): value is string | number => typeof value === 'string' || typeof value === 'number').map((value) => String(value)).join(' ');
    expect(filteredTexts).toMatch(/1\s+noeuds\s+·\s+0\s+aretes/);

    act(() => {
      findPressableByLabel(tree, 'Ouvrir')?.props.onPress();
    });

    expect(mockPush).toHaveBeenCalled();
  });

  it('initializes the tag filter from route params', () => {
    mockGraphSearchParams = { tag: 'nasa' };

    let tree!: renderer.ReactTestRenderer;
    act(() => {
      tree = renderer.create(<GraphScreen />);
    });
    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    }).filter((value): value is string | number => typeof value === 'string' || typeof value === 'number').map((value) => String(value));

    expect(texts).toContain('#nasa');
  });
});