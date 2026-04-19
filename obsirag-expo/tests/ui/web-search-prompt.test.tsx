import React from 'react';
import renderer from 'react-test-renderer';
import { Text, TextInput } from 'react-native';

import { WebSearchPrompt } from '../../components/chat/web-search-prompt';

describe('WebSearchPrompt', () => {
  it('emits query edits and supports use-in-chat action', () => {
    const changes: string[] = [];
    const actions: string[] = [];

    const tree = renderer.create(
      <WebSearchPrompt
        value="Ada Lovelace"
        onChangeText={(value) => changes.push(value)}
        onSubmit={() => actions.push('submit')}
        onUseInChat={() => actions.push('chat')}
      />,
    );

    const input = tree.root.findByType(TextInput);
    input.props.onChangeText('Grace Hopper');

    const chatButtonLabel = tree.root.findAllByType(Text).find((node) => node.props.children === 'Utiliser dans le chat');
    expect(chatButtonLabel).toBeTruthy();

    const chatButton = tree.root.findAll((node) => typeof node.props.onPress === 'function').find((node) => {
      const textChildren = node.findAllByType(Text).flatMap((textNode) => {
        const value = textNode.props.children;
        return Array.isArray(value) ? value : [value];
      });
      return textChildren.includes('Utiliser dans le chat');
    });

    chatButton?.props.onPress();

    expect(changes).toEqual(['Grace Hopper']);
    expect(actions).toEqual(['chat']);
  });

  it('shows both search actions', () => {
    const tree = renderer.create(
      <WebSearchPrompt
        value="Ada Lovelace"
        onChangeText={() => undefined}
        onSubmit={() => undefined}
        onUseInChat={() => undefined}
      />,
    );

    const texts = tree.root.findAllByType(Text).flatMap((node) => {
      const value = node.props.children;
      return Array.isArray(value) ? value : [value];
    });
    const joined = texts.filter((value): value is string => typeof value === 'string').join(' ');

    expect(joined).toMatch(/Recherche sur le web/);
    expect(joined).toMatch(/Lancer la recherche/);
    expect(joined).toMatch(/Utiliser dans le chat/);
  });
});