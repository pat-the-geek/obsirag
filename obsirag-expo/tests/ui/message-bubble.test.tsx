import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

import { MessageBubble } from '../../components/chat/message-bubble';
import { MarkdownNote } from '../../components/notes/markdown-note';
import { ChatMessage } from '../../types/domain';

function findPressableByLabel(tree: renderer.ReactTestRenderer, label: string) {
  return tree.root.findAll((node) => {
    if (typeof node.props.onPress !== 'function') {
      return false;
    }
    return node.findAllByType(Text).some((textNode) => textNode.props.children === label);
  })[0];
}

function collectText(value: unknown): string[] {
  if (typeof value === 'string' || typeof value === 'number') {
    return [String(value)];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => collectText(item));
  }
  if (value && typeof value === 'object' && 'props' in value) {
    return collectText((value as { props?: { children?: unknown } }).props?.children);
  }
  return [];
}

function findHighlightByText(tree: renderer.ReactTestRenderer, expected: string) {
  return tree.root.findAllByProps({ testID: 'markdown-inline-entity-highlight' }).find((node) => collectText(node.props.children).join('') === expected);
}

describe('MessageBubble', () => {
  it('renders a user question without role or unknown provenance labels', () => {
    const message: ChatMessage = {
      id: 'user-1',
      role: 'user',
      content: 'Ou en est Artemis II ?',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'unknown',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      return collectText(node.props.children);
    });
    const joined = texts.filter((value): value is string => typeof value === 'string').join(' ');

    expect(joined).toMatch(/Ou en est Artemis II/);
    expect(joined).not.toMatch(/Vous/);
    expect(joined).not.toMatch(/unknown/i);
  });

  it('hides the fallback placeholder bubble once DDG enrichment is available', () => {
    const message: ChatMessage = {
      id: 'assistant-1',
      role: 'assistant',
      content: "Cette information n'est pas dans ton coffre.",
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      sentinel: true,
      queryOverview: {
        query: 'Ada Lovelace',
        searchQuery: 'Ada Lovelace biography overview',
        summary: 'Ada Lovelace est une pionniere de l\'informatique.',
        sources: [],
      },
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    const joined = tree.root
      .findAllByType(Text)
      .flatMap((node) => collectText(node.props.children))
      .filter((value): value is string => typeof value === 'string')
      .join(' ');

    expect(joined).not.toMatch(/Cette information n'est pas dans ton coffre/);
  });

  it('renders the DDG follow-up as formatted markdown content', () => {
    const message: ChatMessage = {
      id: 'assistant-2',
      role: 'assistant',
      content: '# Vue d\'ensemble DDG\n\n- **Un court paragraphe d\'ensemble :**\nThe Boring Company est une entreprise fondee par Elon Musk.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'web',
      queryOverview: {
        query: 'The Boring Company',
        searchQuery: 'The Boring Company overview',
        summary: '- **Un court paragraphe d\'ensemble :**\nThe Boring Company est une entreprise fondee par Elon Musk.',
        sources: [],
      },
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const markdownNodes = tree.root.findAllByType(MarkdownNote);

    expect(tree.root.findByProps({ testID: 'message-query-overview-response' })).toBeTruthy();
    expect(markdownNodes[0]?.props.markdown).toContain('The Boring Company est une entreprise fondee par Elon Musk.');
    expect(markdownNodes[0]?.props.markdown).toContain('## Un court paragraphe d\'ensemble');
    expect(markdownNodes[0]?.props.markdown).not.toContain('- **Un court paragraphe d\'ensemble :**');
  });

  it('does not render completed-response helper metadata and action buttons', () => {
    const message: ChatMessage = {
      id: 'assistant-5',
      role: 'assistant',
      content: '## Napoleon\n\nVoici une reponse structuree.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      sentinel: true,
      timeline: ['Analyse de la requete', 'Preparation du contexte'],
      stats: {
        tokens: 7,
        ttft: 0,
        total: 0,
        tps: 0,
      },
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      return collectText(node.props.children);
    });
    const joined = texts.filter((value): value is string => typeof value === 'string').join(' ');

    expect(joined).not.toMatch(/Analyse de la requete/);
    expect(joined).not.toMatch(/Preparation du contexte/);
    expect(joined).not.toMatch(/Reponse de repli/);
    expect(joined).not.toMatch(/tokens/);
    expect(joined).not.toMatch(/Relancer/);
    expect(joined).not.toMatch(/Partager/);
    expect(joined).not.toMatch(/Web/);
    expect(joined).not.toMatch(/Requete/);
  });

  it('renders sources inline with the assistant response', () => {
    const noteCalls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-sources',
      role: 'assistant',
      content: 'Voici la reponse associee a ses sources.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      sources: [
        {
          filePath: 'Notes/Ada.md',
          noteTitle: 'Ada',
        },
      ],
    };

    const tree = renderer.create(<MessageBubble message={message} onOpenNote={(path) => noteCalls.push(path)} />);

    expect(() => tree.root.findByProps({ testID: 'sources-panel-content' })).toThrow();

    act(() => {
      tree.root.findByProps({ testID: 'sources-panel-toggle' }).props.onPress();
    });

    expect(tree.root.findByProps({ testID: 'sources-panel-content' })).toBeTruthy();
    expect(tree.root.findAllByType(Text).some((node) => node.props.children === 'Ada')).toBe(true);

    const sourcePressable = tree.root.findAll((node) => typeof node.props.onPress === 'function').find((node) =>
      node.findAllByType(Text).some((textNode) => textNode.props.children === 'Notes/Ada.md'),
    );
    sourcePressable?.props.onPress();

    expect(noteCalls).toEqual(['Notes/Ada.md']);
  });

  it('uses a light assistant bubble palette', () => {
    const message: ChatMessage = {
      id: 'assistant-light',
      role: 'assistant',
      content: 'Reponse affichee sur fond clair.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const bubble = tree.root.findAllByType('View').find((node) => {
      const style = node.props.style;
      if (!Array.isArray(style)) {
        return false;
      }
      return style.some((item) => item?.backgroundColor === '#f4f1ea');
    });

    expect(bubble).toBeTruthy();
    expect(tree.root.findByType(MarkdownNote).props.tone).toBe('light');
  });

  it('wraps assistant responses in a reveal shell', () => {
    const message: ChatMessage = {
      id: 'assistant-reveal',
      role: 'assistant',
      content: 'Une reponse qui apparait progressivement.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    expect(tree.root.findByProps({ testID: 'assistant-reveal-shell' })).toBeTruthy();
  });

  it('renders detailed web sources for enriched answers', () => {
    const message: ChatMessage = {
      id: 'assistant-4',
      role: 'assistant',
      content: '# Vue d\'ensemble DDG\n\nAda Lovelace est une pionniere de l\'informatique.\n\n## Sources\n\n- [Wikipedia](https://example.com/ada)',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'web',
      queryOverview: {
        query: 'Ada Lovelace',
        searchQuery: 'Ada Lovelace biography overview',
        summary: 'Ada Lovelace est une pionniere de l\'informatique.',
        sources: [
          {
            title: 'Wikipedia',
            href: 'https://example.com/ada',
            body: 'Mathematicienne et pionniere de la programmation.',
            domain: 'example.com',
            publishedAt: '2026-04-16',
          },
        ],
      },
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const markdownNodes = tree.root.findAllByType(MarkdownNote);

    expect(markdownNodes[0]?.props.markdown).toContain('[Wikipedia](https://example.com/ada)');
    expect(tree.root.findByProps({ testID: 'message-query-overview-response' })).toBeTruthy();
  });

  it('offers a direct web-search action for assistant answers', () => {
    const searchCalls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-web-search',
      role: 'assistant',
      content: 'Voici un premier niveau de reponse.',
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        webSearchSuggestion="Elon Musk salary 2026"
        onSuggestWebSearch={(query) => searchCalls.push(query)}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'message-web-search-action' }).props.onPress();
    });

    expect(searchCalls).toEqual(['Elon Musk salary 2026']);
  });

  it('offers a delete action for assistant responses', () => {
    const deleteCalls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-delete',
      role: 'assistant',
      content: 'Reponse a supprimer.',
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(<MessageBubble message={message} onDeleteMessage={(messageId) => deleteCalls.push(messageId)} />);

    act(() => {
      tree.root.findByProps({ testID: 'message-delete-action' }).props.onPress();
    });

    expect(deleteCalls).toEqual(['assistant-delete']);
  });

  it('offers the web-search action for mixed vault-miss answers too', () => {
    const searchCalls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-web-search-mixed',
      role: 'assistant',
      content:
        "Cette information n'est pas dans ton coffre. Les extraits disponibles ne mentionnent pas le revenu annuel d'Elon Musk ni les compagnies dans lesquelles il a des actions.",
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        webSearchSuggestion="Elon Musk salary stock holdings 2026"
        onSuggestWebSearch={(query) => searchCalls.push(query)}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'message-web-search-action' }).props.onPress();
    });

    expect(searchCalls).toEqual(['Elon Musk salary stock holdings 2026']);
  });

  it('still shows the web-search action when a sentinel message already has a DDG overview', () => {
    const searchCalls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-web-search-overview',
      role: 'assistant',
      content: "Cette information n'est pas dans ton coffre.",
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
      sentinel: true,
      queryOverview: {
        query: 'Elon Musk salary',
        searchQuery: 'Elon Musk salary 2026',
        summary: 'Resume DDG',
        sources: [],
      },
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        webSearchSuggestion="Elon Musk salary 2026"
        onSuggestWebSearch={(query) => searchCalls.push(query)}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'message-web-search-action' }).props.onPress();
    });

    expect(searchCalls).toEqual(['Elon Musk salary 2026']);
  });

  it('does not offer a web-search action for the streaming assistant placeholder', () => {
    const message: ChatMessage = {
      id: 'streaming-assistant',
      role: 'assistant',
      content: 'Generation en cours...',
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        webSearchSuggestion="Ada Lovelace biography"
        onSuggestWebSearch={() => undefined}
      />,
    );

    expect(tree.root.findAllByProps({ testID: 'message-web-search-action' })).toHaveLength(0);
  });

  it('highlights detected entity names in assistant messages with a type-based color', () => {
    const message: ChatMessage = {
      id: 'assistant-highlight',
      role: 'assistant',
      content: 'Elon Musk dirige Tesla et SpaceX.',
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        highlightEntities={[
          { value: 'Elon Musk', type: 'person' },
          { value: 'Tesla', type: 'organization' },
        ]}
      />,
    );

    const highlights = tree.root.findAllByProps({ testID: 'markdown-inline-entity-highlight' });
    const elonHighlight = findHighlightByText(tree, 'Elon Musk');
    const teslaHighlight = findHighlightByText(tree, 'Tesla');

    expect([...new Set(highlights.flatMap((node) => collectText(node.props.children)))]).toEqual(['Elon Musk', 'Tesla']);
    expect(elonHighlight?.props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({ backgroundColor: '#cfe8ff', color: '#163a56' })]),
    );
    expect(teslaHighlight?.props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({ backgroundColor: '#ffe4b8', color: '#5c3900' })]),
    );
  });

  it('highlights detected entity names in user messages too', () => {
    const message: ChatMessage = {
      id: 'user-highlight',
      role: 'user',
      content: 'Que sais-tu de Paris et Elon Musk ?',
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'unknown',
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        highlightEntities={[
          { value: 'Paris', type: 'location' },
          { value: 'Elon Musk', type: 'person' },
        ]}
      />,
    );

    const highlights = tree.root.findAllByProps({ testID: 'markdown-inline-entity-highlight' });
    const parisHighlight = findHighlightByText(tree, 'Paris');

    expect([...new Set(highlights.flatMap((node) => collectText(node.props.children)))]).toEqual(['Paris', 'Elon Musk']);
    expect(parisHighlight?.props.style).toEqual(
      expect.arrayContaining([expect.objectContaining({ backgroundColor: '#38684a', color: '#eefbe8' })]),
    );
  });

  it('keeps detected entities collapsed by default and renders the markdown table on demand', () => {
    const message: ChatMessage = {
      id: 'assistant-6',
      role: 'assistant',
      content: 'Napoleon est mentionne dans la reponse.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      entityContexts: [
        {
          type: 'person',
          typeLabel: 'Personne',
          value: 'Napoleon Bonaparte',
          mentions: 4,
          lineNumber: 18,
          relationExplanation: 'Napoleon Bonaparte est mentionné dans la note source comme sujet central de ce passage.',
          imageUrl: 'https://example.com/napoleon.png',
          tag: 'Napoleon',
          notes: [
            {
              title: 'Napoleon',
              filePath: 'People/Napoleon.md',
            },
          ],
          ddgKnowledge: {
            heading: 'Napoleon Bonaparte',
            abstractText: 'Empereur des Francais et figure militaire majeure.',
            answer: 'Empereur des Francais',
            answerType: 'person',
            definition: 'Chef militaire et homme d Etat.',
            infobox: [
              { label: 'Naissance', value: '1769' },
            ],
            relatedTopics: [
              { text: 'Bataille de Waterloo', url: 'https://example.com/waterloo' },
            ],
          },
        },
      ],
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    expect(() => tree.root.findByProps({ testID: 'entity-contexts-panel-content' })).toThrow();

    act(() => {
      tree.root.findByProps({ testID: 'entity-contexts-panel-toggle' }).props.onPress();
    });

    expect(tree.root.findByProps({ testID: 'entity-contexts-panel-content' })).toBeTruthy();
    const markdownTable = tree.root.findByProps({ testID: 'markdown-table' });
    const joined = markdownTable.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' ');

    expect(joined).toContain('N°');
    expect(joined).toContain("Nom de l'entité");
    expect(joined).toContain('Napoleon Bonaparte');
    expect(joined).toContain('1');
    expect(joined).toContain('comme sujet central de ce passage');
  });

  it('opens internal wikilinks from assistant markdown', () => {
    const calls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-3',
      role: 'assistant',
      content: 'Voir aussi [[Space/Artemis II|Artemis II]].',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(<MessageBubble message={message} onOpenNote={(notePath) => calls.push(notePath)} />);
    const noteLink = tree.root.findAllByType(Text).find((node) => node.props.children === 'Artemis II');

    expect(noteLink).toBeTruthy();
    noteLink?.props.onPress();
    expect(calls).toEqual(['Space/Artemis II.md']);
  });
});