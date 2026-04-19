import React from 'react';
import renderer, { act } from 'react-test-renderer';

import { MermaidDiagram } from '../../components/markdown/mermaid-diagram.web';

describe('MermaidDiagram web', () => {
  const originalWindow = globalThis.window;
  const originalDocument = globalThis.document;

  afterEach(() => {
    if (originalWindow === undefined) {
      delete (globalThis as typeof globalThis & { window?: Window }).window;
    } else {
      Object.defineProperty(globalThis, 'window', { value: originalWindow, configurable: true, writable: true });
    }

    if (originalDocument === undefined) {
      delete (globalThis as typeof globalThis & { document?: Document }).document;
    } else {
      Object.defineProperty(globalThis, 'document', { value: originalDocument, configurable: true, writable: true });
    }
  });

  it('does not rerender mermaid when local UI state changes', async () => {
    const initialize = jest.fn();
    const render = jest.fn(async () => ({ svg: '<svg><g><text>Diagram</text></g></svg>' }));

    Object.defineProperty(globalThis, 'window', {
      value: { mermaid: { initialize, render } },
      configurable: true,
      writable: true,
    });
    Object.defineProperty(globalThis, 'document', {
      value: {},
      configurable: true,
      writable: true,
    });

    let tree!: renderer.ReactTestRenderer;
    await act(async () => {
      tree = renderer.create(<MermaidDiagram code={'flowchart TD\nA[Start]-->B[Done]'} />);
    });

    expect(render).toHaveBeenCalledTimes(1);

    await act(async () => {
      tree.root.findByProps({ testID: 'mermaid-code-toggle' }).props.onPress();
    });

    expect(render).toHaveBeenCalledTimes(1);
  });
});