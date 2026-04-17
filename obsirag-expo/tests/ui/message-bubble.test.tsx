import React from 'react';
import renderer from 'react-test-renderer';
import { Text } from 'react-native';

import { MessageBubble } from '../../components/chat/message-bubble';
import { ChatMessage } from '../../types/domain';

describe('MessageBubble', () => {
  it('shows guided web-search CTA for sentinel answers', () => {
    const calls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-1',
      role: 'assistant',
      content: "Cette information n'est pas dans ton coffre.",
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      sentinel: true,
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        webSearchSuggestion="Ada Lovelace"
        onSuggestWebSearch={(query) => calls.push(query)}
      />,
    );

    const buttonLabel = tree.root.findAllByType(Text).find((node) => node.props.children === 'Preparer une recherche web');
    expect(buttonLabel).toBeTruthy();

    const pressableNode = tree.root.findAll((node) => typeof node.props.onPress === 'function')[0];
    expect(pressableNode).toBeTruthy();

    pressableNode?.props.onPress();
    expect(calls).toEqual(['Ada Lovelace']);
  });

  it('renders web overview summary when available', () => {
    const calls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-2',
      role: 'assistant',
      content: '# Vue d\'ensemble DDG',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'web',
      queryOverview: {
        query: 'Ada Lovelace',
        searchQuery: 'Ada Lovelace biography overview',
        summary: 'Ada Lovelace est une pionniere de l\'informatique.',
        sources: [],
      },
    };

    const tree = renderer.create(<MessageBubble message={message} onUseQueryInChat={(query) => calls.push(query)} />);
    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    });
    const joined = texts.filter((value): value is string => typeof value === 'string').join(' ');

    expect(joined).toMatch(/Recherche web/);
    expect(joined).toMatch(/pionniere de l'informatique/);
    expect(joined).toMatch(/Utiliser cette requete dans le chat/);
    expect(joined).toMatch(/Partager/);
    expect(joined).toMatch(/Requete/);

    const pressableNodes = tree.root.findAll((node) => typeof node.props.onPress === 'function');
    pressableNodes[0]?.props.onPress();
    expect(calls).toEqual(['Ada Lovelace biography overview']);
  });

  it('shows assistant action bar buttons for prompt reuse and source opening', () => {
    const reuseCalls: string[] = [];
    const sourceCalls: string[] = [];
    const message: ChatMessage = {
      id: 'assistant-5',
      role: 'assistant',
      content: '## Napoleon\n\nVoici une reponse structuree.',
      createdAt: '2026-04-16T12:00:00Z',
      provenance: 'vault',
      primarySource: {
        filePath: 'People/Napoleon.md',
        noteTitle: 'Napoleon',
      },
    };

    const tree = renderer.create(
      <MessageBubble
        message={message}
        replyPrompt="fais un resume de sa vie"
        onReusePrompt={(query) => reuseCalls.push(query)}
        onOpenPrimarySource={(path) => sourceCalls.push(path)}
      />,
    );

    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    });
    const joined = texts.filter((value): value is string => typeof value === 'string').join(' ');

    expect(joined).toMatch(/Relancer/);
    expect(joined).toMatch(/Partager/);
    expect(joined).toMatch(/Source/);

    const relancer = tree.root.findAll((node) => typeof node.props.onPress === 'function').find((node) =>
      node.findAllByType(Text).some((textNode) => textNode.props.children === 'Relancer'),
    );
    const source = tree.root.findAll((node) => typeof node.props.onPress === 'function').find((node) =>
      node.findAllByType(Text).some((textNode) => textNode.props.children === 'Source'),
    );

    relancer?.props.onPress();
    source?.props.onPress();

    expect(reuseCalls).toEqual(['fais un resume de sa vie']);
    expect(sourceCalls).toEqual(['People/Napoleon.md']);
  });

  it('renders detailed web sources for enriched answers', () => {
    const message: ChatMessage = {
      id: 'assistant-4',
      role: 'assistant',
      content: '# Vue d\'ensemble DDG',
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
    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    });
    const joined = texts.filter((value): value is string => typeof value === 'string').join(' ');

    expect(joined).toMatch(/Wikipedia/);
    expect(joined).toMatch(/example.com/);
    expect(joined).toMatch(/2026-04-16/);
    expect(joined).toMatch(/Mathematicienne et pionniere/);
    expect(joined).toMatch(/https:\/\/example.com\/ada/);
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