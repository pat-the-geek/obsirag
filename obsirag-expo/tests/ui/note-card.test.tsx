import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

import { MarkdownNote } from '../../components/notes/markdown-note';
import { NoteCard } from '../../components/notes/note-card';
import { useAppStore } from '../../store/app-store';

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

  it('renders file path, modified date, and size metadata when available', () => {
    const tree = renderer.create(
      <NoteCard
        note={{
          id: 'note-1',
          filePath: 'Dune/note-1.md',
          title: 'Dune',
          bodyMarkdown: 'Contenu',
          tags: [],
          frontmatter: {},
          backlinks: [],
          links: [],
          dateModified: '2026-04-19T14:35:00Z',
          sizeBytes: 12_480,
          noteType: 'user',
        }}
      />,
    );

    const joined = tree.root.findAllByType(Text).map((node) => String(Array.isArray(node.props.children) ? node.props.children.join('') : node.props.children ?? '')).join(' ');

    expect(joined).toContain('Dune/note-1.md');
    expect(joined).toContain('Modifie le');
    expect(joined).toContain('ko');
  });

  it('passes the active dark theme through to markdown rendering', () => {
    const previousThemeMode = useAppStore.getState().themeMode;
    act(() => {
      useAppStore.setState({ themeMode: 'abyss' });
    });

    let tree: renderer.ReactTestRenderer | null = null;

    try {
      act(() => {
        tree = renderer.create(
          <NoteCard
            note={{
              id: 'note-1',
              filePath: 'Dune/note-1.md',
              title: 'Dune',
              bodyMarkdown: '# Titre\n\nContenu sombre',
              tags: [],
              frontmatter: {},
              backlinks: [],
              links: [],
            }}
          />,
        );
      });

      const markdown = tree!.root.findByType(MarkdownNote);

      expect(markdown.props.tone).toBe('dark');
      expect(markdown.props.theme.mode).toBe('abyss');
    } finally {
      act(() => {
        tree?.unmount();
        useAppStore.setState({ themeMode: previousThemeMode });
      });
    }
  });
});