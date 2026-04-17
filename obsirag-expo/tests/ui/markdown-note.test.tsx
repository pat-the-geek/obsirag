import React from 'react';
import renderer from 'react-test-renderer';
import { Text } from 'react-native';

jest.mock('../../components/markdown/http-markdown-image', () => ({
  HttpMarkdownImage: ({ alt, src }: { alt: string; src: string }) => {
    const ReactLocal = require('react');
    const { Text: TextLocal } = require('react-native');
    return ReactLocal.createElement(TextLocal, { testID: 'mock-http-image' }, `${alt}|${src}`);
  },
}));

jest.mock('../../components/markdown/mermaid-diagram', () => ({
  MermaidDiagram: ({ code }: { code: string }) => {
    const ReactLocal = require('react');
    const { Text: TextLocal } = require('react-native');
    return ReactLocal.createElement(TextLocal, { testID: 'mock-mermaid-diagram' }, code);
  },
}));

import { MarkdownNote } from '../../components/notes/markdown-note';

function textTreeContains(tree: renderer.ReactTestRenderer, expected: string) {
  return tree.root.findAllByType(Text).some((node) => {
    const value = node.props.children;
    const parts = Array.isArray(value) ? value : [value];
    return parts.join('').includes(expected);
  });
}

describe('MarkdownNote', () => {
  it('renders inline bold markdown text', () => {
    const tree = renderer.create(
      <MarkdownNote markdown={'**MacBook Air** (13 et 15 pouces, puce M2/M3).'} />,
    );

    expect(textTreeContains(tree, 'MacBook Air')).toBe(true);
  });

  it('renders remote markdown images as dedicated media blocks', () => {
    const tree = renderer.create(
      <MarkdownNote markdown={'![Vue orbitale](https://example.com/orbit.png)'} />,
    );

    const imageNode = tree.root.findByProps({ testID: 'mock-http-image' });
    expect(imageNode.props.children).toBe('Vue orbitale|https://example.com/orbit.png');
  });

  it('renders mermaid fenced blocks through the graphic mermaid component', () => {
    const tree = renderer.create(
      <MarkdownNote
        markdown={[
          '# Diagramme',
          '',
          '```mermaid',
          'flowchart TD',
          '  A[Start] --> B[Done]',
          '```',
        ].join('\n')}
      />,
    );

    const mermaidNode = tree.root.findByProps({ testID: 'mock-mermaid-diagram' });
    expect(mermaidNode.props.children).toContain('flowchart TD');
    expect(mermaidNode.props.children).toContain('A[Start] --> B[Done]');
  });

  it('renders markdown tables as dedicated table blocks', () => {
    const tree = renderer.create(
      <MarkdownNote
        markdown={[
          '| Entité | Type | Rôle |',
          '|--------|------|------|',
          "| Marsha Blackburn | Personnalité politique | Auteure principale du projet de loi |",
          '| Maison Blanche | Institution gouvernementale | Promotrice de règles nationales |',
        ].join('\n')}
      />,
    );

    expect(tree.root.findByProps({ testID: 'markdown-table' })).toBeTruthy();
  });

  it('renders aligned markdown tables and nested ordered lists without falling back to paragraphs', () => {
    const tree = renderer.create(
      <MarkdownNote
        markdown={[
          '| Nom | Score | Statut |',
          '| :--- | ---: | :---: |',
          '| Ada | 42 | OK |',
          '',
          '1. Premiere etape',
          '   1. Sous-etape detaillee',
          '   - Point de controle',
          '2. Deuxieme etape',
        ].join('\n')}
      />,
    );

    expect(tree.root.findByProps({ testID: 'markdown-table' })).toBeTruthy();
    expect(tree.root.findAllByProps({ testID: 'markdown-list-item' }).length).toBeGreaterThanOrEqual(4);
  });

  it('renders markdown table cells with explicit line breaks', () => {
    const tree = renderer.create(
      <MarkdownNote
        markdown={[
          '| Entité | Rôle |',
          '| --- | --- |',
          '| Maison Blanche | Promotrice de règles<br>nationales |',
        ].join('\n')}
      />,
    );

    expect(tree.root.findByProps({ testID: 'markdown-table' })).toBeTruthy();
    expect(tree.root.findAllByProps({ testID: 'markdown-table-cell-multiline' }).length).toBeGreaterThanOrEqual(1);
  });

  it('renders inline hashtags as styled tags inside note text', () => {
    const tree = renderer.create(
      <MarkdownNote
        markdown={[
          'Type: user',
          'Modifiee: 2026-04-12',
          "j'ai regardé à nouveau les 2 premiers épisodes. Quel film ! Je me réjouis du prochain, le #Dune 3.",
          'Je trouve interessant l’image qu’on donne au peuple #Fremen. Visuellement, cela me fait penser à des habitants de #Gaza.',
        ].join('\n')}
      />,
    );

    const tags = tree.root.findAllByProps({ testID: 'markdown-inline-tag' }).map((node) => node.props.children);

    expect(tags).toEqual(expect.arrayContaining(['#Dune', '#Fremen', '#Gaza']));
  });

  it('calls the tag handler when an inline hashtag is pressed', () => {
    const calls: string[] = [];
    const tree = renderer.create(
      <MarkdownNote markdown={'Le prochain film sera #Dune 3.'} onOpenTag={(value) => calls.push(value)} />,
    );

    tree.root.findByProps({ testID: 'markdown-inline-tag' }).props.onPress();

    expect(calls).toEqual(['Dune']);
  });
});