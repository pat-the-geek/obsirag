import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

import { aggregateConversationEntityContexts, buildCompactNoteLabel, ConversationEntitySidebar } from '../../components/chat/conversation-entity-sidebar';
import { useAppStore } from '../../store/app-store';
import { ChatMessage } from '../../types/domain';

function flattenStyle(value: unknown): Array<Record<string, unknown>> {
  if (!value) {
    return [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenStyle(item));
  }
  if (typeof value === 'object') {
    return [value as Record<string, unknown>];
  }
  return [];
}

function collectRenderedText(tree: renderer.ReactTestRenderer): string {
  return tree.root
    .findAllByType(Text)
    .map((node) => {
      const children = node.props.children;
      return Array.isArray(children) ? children.join('') : String(children ?? '');
    })
    .join('\n');
}

describe('ConversationEntitySidebar', () => {
  it('aggregates, deduplicates and sorts entity contexts across the conversation', () => {
    const messages: ChatMessage[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Reponse',
        createdAt: '2026-04-16T12:00:00Z',
        entityContexts: [
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Zulu',
            mentions: 1,
            notes: [{ title: 'Zeta Knowledge Base', filePath: 'Notes/Zeta-Knowledge-Base.md' }],
          },
        ],
      },
      {
        id: 'assistant-2',
        role: 'assistant',
        content: 'Reponse',
        createdAt: '2026-04-16T12:00:01Z',
        entityContexts: [
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            mentions: 2,
            notes: [{ title: 'Alpha Research Notebook', filePath: 'Notes/Alpha-Research-Notebook.md' }],
          },
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Zulu',
            mentions: 3,
            notes: [{ title: 'Zulu Field Notes', filePath: 'Notes/Zulu-Field-Notes.md' }],
          },
        ],
      },
    ];

    const entities = aggregateConversationEntityContexts(messages);

    expect(entities.map((entity) => entity.value)).toEqual(['Alpha', 'Zulu']);
    expect(entities[1]?.mentions).toBe(4);
    expect(entities[1]?.notes.map((note) => note.filePath)).toEqual(['Notes/Zeta-Knowledge-Base.md', 'Notes/Zulu-Field-Notes.md']);
  });

  it('truncates related note labels from the start of the note name', () => {
    expect(buildCompactNoteLabel({ title: 'Alpha Research Notebook', filePath: 'Notes/Alpha-Research-Notebook.md' }, 112)).toBe('Alpha Research Not…');
  });

  it('renders related note pills that open the linked note', () => {
    const noteCalls: string[] = [];
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            imageUrl: 'https://example.com/alpha.png',
            notes: [{ title: 'Alpha Research Notebook', filePath: 'Notes/Alpha-Research-Notebook.md' }],
          },
        ]}
        onOpenNote={(path) => noteCalls.push(path)}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'entity-note-pill' }).props.onPress();
    });

    expect(noteCalls).toEqual(['Notes/Alpha-Research-Notebook.md']);
  });

  it('renders metadata for related notes when available', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            notes: [
              {
                title: 'Alpha Research Notebook',
                filePath: 'Notes/Alpha-Research-Notebook.md',
                dateModified: '2026-04-19T14:35:00Z',
                sizeBytes: 4096,
              },
            ],
          },
        ]}
      />,
    );

    const renderedText = collectRenderedText(tree);

    expect(renderedText).toContain('4 ko');
  });

  it('renders the entity cards inside a dedicated scroll container', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            notes: [],
          },
        ]}
        maxHeight={420}
      />,
    );

    expect(tree.root.findByProps({ testID: 'conversation-entity-sidebar-scroll' })).toBeTruthy();
  });

  it('defaults the entity filter to Personne when available', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Amy Adams',
            notes: [],
          },
          {
            type: 'location',
            typeLabel: 'Lieu',
            value: 'Arrakis',
            notes: [],
          },
        ]}
      />,
    );

    const renderedText = collectRenderedText(tree);

    expect(renderedText).toContain('Amy Adams');
    expect(renderedText).not.toContain('Arrakis');
    expect(renderedText).toContain('Personne');
    expect(renderedText).toContain('1 entree sur 2');
  });

  it('can switch the entity filter back to all entity types', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Amy Adams',
            notes: [],
          },
          {
            type: 'location',
            typeLabel: 'Lieu',
            value: 'Arrakis',
            notes: [],
          },
        ]}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'entity-type-filter-trigger' }).props.onPress();
    });

    act(() => {
      tree.root.findByProps({ testID: 'entity-type-filter-option-all' }).props.onPress();
    });

    const renderedText = collectRenderedText(tree);

    expect(renderedText).toContain('Amy Adams');
    expect(renderedText).toContain('Arrakis');
    expect(renderedText).toContain('2 entrees');
  });

  it('uses the active custom dark theme for the sidebar and cards', () => {
    const previousThemeMode = useAppStore.getState().themeMode;
    act(() => {
      useAppStore.setState({ themeMode: 'abyss' });
    });

    let tree: renderer.ReactTestRenderer | undefined;

    try {
      tree = renderer.create(
        <ConversationEntitySidebar
          entities={[
            {
              type: 'person',
              typeLabel: 'Personne',
              value: 'Amy Adams',
              notes: [],
            },
          ]}
        />,
      );

      const sidebar = tree.root.findByProps({ testID: 'conversation-entity-sidebar' });
      const sidebarStyle = flattenStyle(sidebar.props.style);
      const card = tree.root.findByProps({ testID: 'conversation-entity-card' });
      const cardStyle = flattenStyle(card.props.style);

      expect(sidebarStyle).toEqual(
        expect.arrayContaining([expect.objectContaining({ backgroundColor: '#061a2b', borderColor: '#163956' })]),
      );
      expect(cardStyle).toEqual(
        expect.arrayContaining([expect.objectContaining({ backgroundColor: '#0b2235', borderColor: '#163956' })]),
      );
    } finally {
      tree?.unmount();
      act(() => {
        useAppStore.setState({ themeMode: previousThemeMode });
      });
    }
  });
});