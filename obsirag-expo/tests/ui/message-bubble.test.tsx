import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text, View } from 'react-native';

import { MessageBubble } from '../../components/chat/message-bubble';
import { MarkdownNote } from '../../components/notes/markdown-note';
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

function normalizeInlineText(value: string) {
  return value.replace(/\s+/g, ' ').trim();
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

  it('keeps the user message shell anchored to the right edge', () => {
    const message: ChatMessage = {
      id: 'user-right-aligned',
      role: 'user',
      content: 'Message aligne a droite',
      createdAt: '2026-04-18T12:00:00Z',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const shell = tree.root.findByProps({ testID: 'user-message-shell' });
    const bubble = tree.root.findByProps({ testID: 'user-message-bubble' });
    const bubbleStyle = flattenStyle(bubble.props.style);

    expect(shell.props.style).toEqual(expect.arrayContaining([expect.objectContaining({ width: '100%', alignItems: 'flex-end' })]));
    expect(bubbleStyle).toEqual(
      expect.arrayContaining([expect.objectContaining({ alignSelf: 'flex-end', marginLeft: 'auto' })]),
    );
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

  it('renders the generating provider badge on standard assistant responses', () => {
    const message: ChatMessage = {
      id: 'assistant-provider-main',
      role: 'assistant',
      content: 'Reponse generee par Euria.',
      createdAt: '2026-04-20T12:00:00Z',
      provenance: 'vault',
      llmProvider: 'Euria',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const texts = tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children));
    const joined = texts.join(' ');

    expect(joined).toMatch(/ObsiRAG/);
    expect(joined).toMatch(/coffre/);
    expect(joined).toMatch(/via Euria/);
  });

  it('renders a lowercase web provenance badge for web answers', () => {
    const message: ChatMessage = {
      id: 'assistant-web-badge',
      role: 'assistant',
      content: 'Réponse issue du web.',
      createdAt: '2026-04-20T12:00:00Z',
      provenance: 'web',
      llmProvider: 'Euria',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const joined = tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' ');

    expect(joined).toMatch(/web/);
    expect(joined).toMatch(/via Euria/);
  });

  it('passes the full assistant markdown to the renderer without incremental truncation', () => {
    const message: ChatMessage = {
      id: 'assistant-full-markdown',
      role: 'assistant',
      content: '🌟 Clés pour comprendre les rôles :\n\n- Maison Atreides : Noble, honorable, mais détruite au début.\n- Béné Gesserit : Ordre secret influent.',
      createdAt: '2026-04-20T12:00:00Z',
      provenance: 'vault',
      llmProvider: 'Euria',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const markdownNode = tree.root.findByType(MarkdownNote);

    expect(markdownNode.props.markdown).toBe(message.content);
  });

  it('renders the DDG follow-up as formatted markdown content', () => {
    const message: ChatMessage = {
      id: 'assistant-2',
      role: 'assistant',
      content: '# Vue d\'ensemble DDG\n\n- **Un court paragraphe d\'ensemble :**\nThe Boring Company est une entreprise fondee par Elon Musk.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'web',
      llmProvider: 'MLX',
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
    expect(tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' ')).toMatch(/via MLX/);
  });

  it('renders compact generation stats for completed assistant responses', () => {
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
    expect(joined).toMatch(/7 tokens/);
    expect(joined).toMatch(/0 tok\/s/);
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

  it('deduplicates repeated assistant sources before rendering the list', () => {
    const message: ChatMessage = {
      id: 'assistant-sources-deduped',
      role: 'assistant',
      content: 'Voici la reponse associee a ses sources.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      sources: [
        {
          filePath: 'Notes/Ada.md',
          noteTitle: 'Ada',
          score: 0.42,
        },
        {
          filePath: './Notes/Ada.md',
          noteTitle: ' Ada ',
          score: 0.99,
          isPrimary: true,
        },
        {
          filePath: 'Notes/Charles.md',
          noteTitle: 'Charles',
        },
      ],
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    act(() => {
      tree.root.findByProps({ testID: 'sources-panel-toggle' }).props.onPress();
    });

    const texts = tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children));
    const joined = texts.join('');
    expect(texts.filter((value) => value === 'Ada')).toHaveLength(1);
    expect(joined).toContain('2 sources');
    expect(texts).toContain('Notes/Charles.md');
  });

  it('uses the active light theme palette for the assistant bubble', () => {
    const message: ChatMessage = {
      id: 'assistant-light',
      role: 'assistant',
      content: 'Reponse affichee sur fond clair.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const bubble = tree.root.findByProps({ testID: 'assistant-message-bubble' });
    const bubbleStyle = flattenStyle(bubble.props.style);

    expect(bubbleStyle).toEqual(
      expect.arrayContaining([expect.objectContaining({ backgroundColor: '#ffffff', borderColor: '#d7deea' })]),
    );
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

  it('does not render a separate DDG follow-up for hybrid answers', () => {
    const message: ChatMessage = {
      id: 'assistant-hybrid-overview',
      role: 'assistant',
      content: '## Reponse principale\n\nContenu du coffre affiche dans la bulle principale.',
      createdAt: '2026-04-19T12:00:00Z',
      provenance: 'hybrid',
      queryOverview: {
        query: 'Qui a fait le premier pas sur la lune ?',
        searchQuery: 'Qui a fait le premier pas sur la lune ? explication analyse histoire contexte',
        summary: 'Neil Armstrong a pose le premier pas sur la Lune lors d\'Apollo 11.',
        sources: [],
      },
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const markdownNodes = tree.root.findAllByType(MarkdownNote);
    const joined = tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' ');

    expect(markdownNodes).toHaveLength(1);
    expect(markdownNodes[0]?.props.markdown).toContain('Contenu du coffre affiche dans la bulle principale.');
    expect(tree.root.findAllByProps({ testID: 'message-query-overview-response' })).toHaveLength(0);
    expect(joined).toMatch(/web \+ coffre/);
  });

  it('keeps the main assistant response visible when Mermaid content is present alongside a DDG overview', () => {
    const message: ChatMessage = {
      id: 'assistant-web-mermaid',
      role: 'assistant',
      content: ['```mermaid', 'flowchart TD', '  A[Question] --> B[Reponse]', '```'].join('\n'),
      createdAt: '2026-04-18T12:00:00Z',
      provenance: 'web',
      queryOverview: {
        query: 'diagramme mermaid',
        searchQuery: 'diagramme mermaid flowchart example',
        summary: 'Resume DDG',
        sources: [],
      },
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const markdownNodes = tree.root.findAllByType(MarkdownNote);

    expect(tree.root.findByProps({ testID: 'assistant-reveal-shell' })).toBeTruthy();
    expect(tree.root.findByProps({ testID: 'message-query-overview-response' })).toBeTruthy();
    expect(markdownNodes.some((node) => String(node.props.markdown).includes('```mermaid'))).toBe(true);
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

  it('renders an explicit pending assistant state before any response content is available', () => {
    const message: ChatMessage = {
      id: 'streaming-assistant',
      role: 'assistant',
      content: '',
      createdAt: '2026-04-17T12:00:00Z',
      provenance: 'vault',
      timeline: ['Réponse en préparation', 'Recherche dans le coffre'],
    };

    const tree = renderer.create(<MessageBubble message={message} />);
    const texts = tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children));
    const joined = texts.join(' ');

    expect(tree.root.findByProps({ testID: 'assistant-pending-state' })).toBeTruthy();
    expect(joined).toMatch(/Réponse en préparation/);
    expect(joined).toMatch(/Recherche dans le coffre/);
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

  it('renders the detected entities panel with the active custom theme instead of Light+', () => {
    const previousThemeMode = useAppStore.getState().themeMode;
    act(() => {
      useAppStore.setState({ themeMode: 'quiet' });
    });

    let tree: renderer.ReactTestRenderer | undefined;

    try {
      const message: ChatMessage = {
        id: 'assistant-entities-theme',
        role: 'assistant',
        content: 'Napoleon est mentionne dans la reponse.',
        createdAt: '2026-04-16T12:00:00Z',
        provenance: 'vault',
        entityContexts: [
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Napoleon Bonaparte',
            relationExplanation: 'Napoleon Bonaparte est relie a la reponse.',
            notes: [],
          },
        ],
      };

      tree = renderer.create(<MessageBubble message={message} />);

      act(() => {
        tree.root.findByProps({ testID: 'entity-contexts-panel-toggle' }).props.onPress();
      });

      const panel = tree.root.findByProps({ testID: 'entity-contexts-panel' });
      const panelStyle = flattenStyle(panel.props.style);
      const tableSurface = tree.root.findByProps({ testID: 'markdown-table-surface' });
      const tableStyle = flattenStyle(tableSurface.props.style);

      expect(panelStyle).toEqual(
        expect.arrayContaining([expect.objectContaining({ backgroundColor: '#f0f3f6', borderColor: '#d4dbe3' })]),
      );
      expect(tableStyle).toEqual(
        expect.arrayContaining([expect.objectContaining({ backgroundColor: '#f8fafc', borderColor: '#d4dbe3' })]),
      );
    } finally {
      tree?.unmount();
      act(() => {
        useAppStore.setState({ themeMode: previousThemeMode });
      });
    }
  });

  it('renders the detected entities panel with the active custom dark theme instead of Dark+', () => {
    const previousThemeMode = useAppStore.getState().themeMode;
    act(() => {
      useAppStore.setState({ themeMode: 'abyss' });
    });

    let tree: renderer.ReactTestRenderer | undefined;

    try {
      const message: ChatMessage = {
        id: 'assistant-entities-theme-abyss',
        role: 'assistant',
        content: 'Arrakis est mentionne dans la reponse.',
        createdAt: '2026-04-16T12:00:00Z',
        provenance: 'vault',
        entityContexts: [
          {
            type: 'location',
            typeLabel: 'Lieu',
            value: 'Arrakis',
            relationExplanation: 'Arrakis est relie a la reponse.',
            notes: [],
          },
        ],
      };

      tree = renderer.create(<MessageBubble message={message} />);

      act(() => {
        tree.root.findByProps({ testID: 'entity-contexts-panel-toggle' }).props.onPress();
      });

      const panel = tree.root.findByProps({ testID: 'entity-contexts-panel' });
      const panelStyle = flattenStyle(panel.props.style);
      const tableSurface = tree.root.findByProps({ testID: 'markdown-table-surface' });
      const tableStyle = flattenStyle(tableSurface.props.style);

      expect(panelStyle).toEqual(
        expect.arrayContaining([expect.objectContaining({ backgroundColor: '#0b2235', borderColor: '#163956' })]),
      );
      expect(tableStyle).toEqual(
        expect.arrayContaining([expect.objectContaining({ backgroundColor: '#061a2b', borderColor: '#163956' })]),
      );
    } finally {
      tree?.unmount();
      act(() => {
        useAppStore.setState({ themeMode: previousThemeMode });
      });
    }
  });

  it('defaults the inline detected entities filter to Personne when available', () => {
    const message: ChatMessage = {
      id: 'assistant-entities-filter-default',
      role: 'assistant',
      content: 'Napoleon et Arrakis sont mentionnes dans la reponse.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      entityContexts: [
        {
          type: 'person',
          typeLabel: 'Personne',
          value: 'Napoleon Bonaparte',
          relationExplanation: 'Napoleon Bonaparte est relie a la reponse.',
          notes: [],
        },
        {
          type: 'location',
          typeLabel: 'Lieu',
          value: 'Arrakis',
          relationExplanation: 'Arrakis est reliee a la reponse.',
          notes: [],
        },
      ],
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    act(() => {
      tree.root.findByProps({ testID: 'entity-contexts-panel-toggle' }).props.onPress();
    });

    const panelText = normalizeInlineText(tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' '));

    expect(panelText).toContain('1 entité sur 2');
    expect(panelText).toContain('Personne');

    const markdownTable = tree.root.findByProps({ testID: 'markdown-table' });
    const joined = normalizeInlineText(markdownTable.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' '));

    expect(joined).toContain('Napoleon Bonaparte');
    expect(joined).not.toContain('Arrakis');
  });

  it('can switch the inline detected entities filter back to all types', () => {
    const message: ChatMessage = {
      id: 'assistant-entities-filter-all',
      role: 'assistant',
      content: 'Napoleon et Arrakis sont mentionnes dans la reponse.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      entityContexts: [
        {
          type: 'person',
          typeLabel: 'Personne',
          value: 'Napoleon Bonaparte',
          relationExplanation: 'Napoleon Bonaparte est relie a la reponse.',
          notes: [],
        },
        {
          type: 'location',
          typeLabel: 'Lieu',
          value: 'Arrakis',
          relationExplanation: 'Arrakis est reliee a la reponse.',
          notes: [],
        },
      ],
    };

    const tree = renderer.create(<MessageBubble message={message} />);

    act(() => {
      tree.root.findByProps({ testID: 'entity-contexts-panel-toggle' }).props.onPress();
    });

    act(() => {
      tree.root.findByProps({ testID: 'entity-contexts-filter-trigger' }).props.onPress();
    });

    const menuTextBeforeSelection = normalizeInlineText(
      tree.root.findByProps({ testID: 'entity-contexts-filter-menu' }).findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' '),
    );

    expect(menuTextBeforeSelection).toContain("Tous les types d'entités");
    expect(menuTextBeforeSelection).toContain('Personne');
    expect(menuTextBeforeSelection).toContain('Lieu');

    act(() => {
      tree.root.findByProps({ testID: 'entity-contexts-filter-option-all' }).props.onPress();
    });

    const panelText = normalizeInlineText(tree.root.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' '));
    expect(panelText).toMatch(/2 entité ?s/);
    expect(panelText).toContain("Tous les types d'entités");

    const markdownTable = tree.root.findByProps({ testID: 'markdown-table' });
    const joined = normalizeInlineText(markdownTable.findAllByType(Text).flatMap((node) => collectText(node.props.children)).join(' '));

    expect(joined).toContain('Napoleon Bonaparte');
    expect(joined).toContain('Arrakis');
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