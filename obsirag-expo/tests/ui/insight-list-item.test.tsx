import React from 'react';
import renderer from 'react-test-renderer';
import { Text } from 'react-native';

import { InsightListItem } from '../../components/insights/insight-list-item';
import { InsightItem } from '../../types/domain';

function findPressableByLabel(tree: renderer.ReactTestRenderer, label: string) {
  return tree.root.findAll((node) => {
    if (typeof node.props.onPress !== 'function') {
      return false;
    }
    return node.findAllByType(Text).some((textNode) => textNode.props.children === label);
  })[0];
}

describe('InsightListItem', () => {
  it('separates main card opening from tag navigation', () => {
    const openCalls: string[] = [];
    const tagCalls: string[] = [];
    const item: InsightItem = {
      id: 'insight-1',
      title: 'Artemis synthesis',
      filePath: 'obsirag/insights/artemis.md',
      kind: 'insight',
      tags: ['nasa', 'mission'],
      excerpt: 'Synthese rapide du programme Artemis.',
    };

    const tree = renderer.create(
      <InsightListItem item={item} onPress={() => openCalls.push(item.id)} onOpenTag={(tag) => tagCalls.push(tag)} />,
    );

    findPressableByLabel(tree, 'Artemis synthesis')?.props.onPress();
    expect(openCalls).toEqual(['insight-1']);

    tree.root.findAllByProps({ testID: 'tag-pill' })[0]?.props.onPress();
    expect(tagCalls).toEqual(['nasa']);
    expect(openCalls).toEqual(['insight-1']);
  });

  it('renders modified date and size metadata when available', () => {
    const item: InsightItem = {
      id: 'insight-2',
      title: 'Rapport Artemis',
      filePath: 'obsirag/insights/rapport-artemis.md',
      kind: 'insight',
      tags: [],
      dateModified: '2026-04-19T14:35:00Z',
      sizeBytes: 12_480,
    };

    const tree = renderer.create(<InsightListItem item={item} />);
    const joined = tree.root.findAllByType(Text).map((node) => String(Array.isArray(node.props.children) ? node.props.children.join('') : node.props.children ?? '')).join(' ');

    expect(joined).toContain('Modifie le');
    expect(joined).toContain('ko');
  });
});