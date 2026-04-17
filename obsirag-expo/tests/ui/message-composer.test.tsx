import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { TextInput } from 'react-native';

import { MessageComposer } from '../../components/chat/message-composer';

describe('MessageComposer', () => {
  it('submits on Enter without requiring a click on Envoyer', () => {
    const submitCalls: string[] = [];
    const tree = renderer.create(
      <MessageComposer value="Quel est son salaire ?" onChangeText={() => undefined} onSubmit={() => submitCalls.push('submit')} />,
    );

    act(() => {
      tree.root.findByType(TextInput).props.onKeyPress({
        nativeEvent: { key: 'Enter' },
        preventDefault: () => undefined,
      });
    });

    expect(submitCalls).toEqual(['submit']);
  });

  it('keeps Shift+Enter available for a newline', () => {
    const submitCalls: string[] = [];
    const tree = renderer.create(
      <MessageComposer value="Question multiligne" onChangeText={() => undefined} onSubmit={() => submitCalls.push('submit')} />,
    );

    act(() => {
      tree.root.findByType(TextInput).props.onKeyPress({
        nativeEvent: { key: 'Enter', shiftKey: true },
        preventDefault: () => undefined,
      });
    });

    expect(submitCalls).toEqual([]);
  });
});