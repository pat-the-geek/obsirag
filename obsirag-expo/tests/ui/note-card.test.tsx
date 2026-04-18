import React from 'react';
import renderer, { act } from 'react-test-renderer';

import { NoteCard } from '../../components/notes/note-card';

describe('NoteCard', () => {
  it('renders note tags as clickable pills', () => {
    const calls: string[] = [];
    const tree = renderer.create(
      <NoteCard
        note={{
          id: 'note-1',
          filePath: 'Dune/note-1.md',
          title: 'Dune',
          bodyMarkdown: 'Je me rejouis de #Dune 3.',
          tags: ['Dune', 'Cinema'],
          frontmatter: {},
          backlinks: [],
          links: [],
          dateModified: '2026-04-12',
          noteType: 'user',
        }}
        onOpenTag={(value) => calls.push(value)}
      />,
    );

    const pills = tree.root.findAll((node) => node.props.testID === 'tag-pill' && typeof node.props.onPress === 'function');
    expect(pills.length).toBeGreaterThanOrEqual(2);

    const firstPill = pills[0];
    expect(firstPill).toBeTruthy();

    act(() => {
      firstPill?.props.onPress();
    });

    expect(calls).toEqual(['Dune']);
  });
});