import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text, TextInput } from 'react-native';

import { MessageComposer } from '../../components/chat/message-composer';

describe('MessageComposer', () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  it('submits on Enter without requiring a click on Envoyer', () => {
    const submitCalls: string[] = [];
    const tree = renderer.create(
      <MessageComposer value="Quel est son salaire ?" onChangeText={() => undefined} onSubmit={(value) => submitCalls.push(value)} />,
    );

    act(() => {
      tree.root.findByType(TextInput).props.onKeyPress({
        nativeEvent: { key: 'Enter' },
        preventDefault: () => undefined,
      });
    });

    expect(submitCalls).toEqual(['Quel est son salaire ?']);
  });

  it('keeps Shift+Enter available for a newline', () => {
    const submitCalls: string[] = [];
    const tree = renderer.create(
      <MessageComposer value="Question multiligne" onChangeText={() => undefined} onSubmit={(value) => submitCalls.push(value)} />,
    );

    act(() => {
      tree.root.findByType(TextInput).props.onKeyPress({
        nativeEvent: { key: 'Enter', shiftKey: true },
        preventDefault: () => undefined,
      });
    });

    expect(submitCalls).toEqual([]);
  });

  it('toggles the Euria checkbox when pressed', () => {
    const toggleCalls: boolean[] = [];
    const tree = renderer.create(
      <MessageComposer
        value="Question"
        onChangeText={() => undefined}
        onSubmit={() => undefined}
        withEuria={false}
        onToggleWithEuria={(value) => toggleCalls.push(value)}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'message-composer-euria-toggle' }).props.onPress();
    });

    expect(toggleCalls).toEqual([true]);
    expect(tree.root.findAllByType(Text).some((node) => node.props.children === 'Avec Euria')).toBe(true);
  });

  it('syncs the draft to the parent after a short idle delay instead of every keystroke', () => {
    const draftCalls: string[] = [];
    const tree = renderer.create(
      <MessageComposer value="" onChangeText={(value) => draftCalls.push(value)} onSubmit={() => undefined} />,
    );

    act(() => {
      tree.root.findByType(TextInput).props.onChangeText('Bon');
      tree.root.findByType(TextInput).props.onChangeText('Bonjour');
    });

    expect(draftCalls).toEqual([]);

    act(() => {
      jest.advanceTimersByTime(180);
    });

    expect(draftCalls).toEqual(['Bonjour']);
  });
});