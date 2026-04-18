import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';
import { WebView } from 'react-native-webview';

import { MermaidDiagram, buildStaticMermaidHtml, normalizeMermaidCode, resolveMermaidLibrary } from '../../components/markdown/mermaid-diagram';

describe('normalizeMermaidCode', () => {
  it('splits chained flowchart statements and quotes labels with strict characters', () => {
    const normalized = normalizeMermaidCode([
      'flowchart TD',
      'A --> B[Dune: Part One (2021)]    A --> C[Dune: Part Two (2024)]',
    ].join('\n'));

    expect(normalized).toContain('A --> B["Dune: Part One (2021)"]');
    expect(normalized).toContain('A --> C["Dune: Part Two (2024)"]');
    expect(normalized.split('\n')).toHaveLength(3);
  });

  it('keeps the mermaid code hidden by default and reveals it in a panel', () => {
    let tree!: renderer.ReactTestRenderer;

    act(() => {
      tree = renderer.create(<MermaidDiagram code={'flowchart TD\nA[Start: phase (1)]-->B'} />);
    });

    expect(tree.root.findAllByProps({ testID: 'mermaid-code-panel-content' })).toHaveLength(0);

    act(() => {
      tree.root.findByProps({ testID: 'mermaid-code-toggle' }).props.onPress();
    });

    expect(tree.root.findByProps({ testID: 'mermaid-code-panel-content' })).toBeTruthy();
    expect(tree.root.findAllByType(Text).some((node) => String(node.props.children).includes('A["Start: phase (1)"]-->B'))).toBe(true);
  });

  it('does not inject the raw mermaid code into the embedded diagram html fallback', () => {
    let tree!: renderer.ReactTestRenderer;

    act(() => {
      tree = renderer.create(<MermaidDiagram code={'flowchart TD\nA[Start]-->B[Done]'} />);
    });

    const webView = tree.root.findByType(WebView);
    const html = String(webView.props.source.html);

    expect(html).toContain('Consultez la rubrique Code Mermaid ci-dessous.');
    expect(html).not.toContain("errorElement.textContent = rawCode");
  });

  it('builds static web html without external mermaid cdn scripts', () => {
    const html = buildStaticMermaidHtml({
      svg: '<svg><g><text>Diagram</text></g></svg>',
      error: null,
    });

    expect(html).toContain('<svg><g><text>Diagram</text></g></svg>');
    expect(html).not.toContain('cdn.jsdelivr.net');
    expect(html).not.toContain('unpkg.com');
    expect(html).not.toContain('<script');
  });

  it('resolves the browser bundle default export shape used by the web renderer', () => {
    const initialize = jest.fn();
    const render = jest.fn(async () => ({ svg: '<svg />' }));

    const mermaid = resolveMermaidLibrary({
      default: {
        initialize,
        render,
      },
    });

    expect(mermaid.initialize).toBe(initialize);
    expect(mermaid.render).toBe(render);
  });
});