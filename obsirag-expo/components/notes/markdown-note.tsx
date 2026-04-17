import { Fragment } from 'react';
import { Linking, StyleSheet, Text, View } from 'react-native';

import { MermaidDiagram } from '../markdown/mermaid-diagram';

type MarkdownNoteProps = {
  markdown: string;
  onOpenNote?: (value: string) => void;
  variant?: 'default' | 'article';
  tone?: 'light' | 'dark';
};

type MarkdownBlock =
  | { type: 'spacer'; content: string }
  | { type: 'heading'; content: string; level: number }
  | { type: 'bullet'; content: string }
  | { type: 'quote'; content: string }
  | { type: 'code'; content: string }
  | { type: 'mermaid'; content: string }
  | { type: 'paragraph'; content: string };

type InlineChunk =
  | { type: 'text'; value: string }
  | { type: 'note-link'; label: string; target: string }
  | { type: 'url-link'; label: string; href: string };

export function MarkdownNote({ markdown, onOpenNote, variant = 'default', tone = 'light' }: MarkdownNoteProps) {
  const lines = markdown.split('\n');
  const blocks: MarkdownBlock[] = [];
  let inCode = false;
  let codeFenceLanguage = '';
  let codeBuffer: string[] = [];

  for (const rawLine of lines) {
    const line = rawLine.replace(/\t/g, '  ');
    if (line.trim().startsWith('```')) {
      if (inCode) {
        blocks.push({ type: codeFenceLanguage === 'mermaid' ? 'mermaid' : 'code', content: codeBuffer.join('\n') });
        codeBuffer = [];
        codeFenceLanguage = '';
      } else {
        codeFenceLanguage = line.trim().slice(3).trim().toLowerCase();
      }
      inCode = !inCode;
      continue;
    }

    if (inCode) {
      codeBuffer.push(line);
      continue;
    }

    if (!line.trim()) {
      blocks.push({ type: 'spacer', content: '' });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading?.[1] && heading[2]) {
      blocks.push({ type: 'heading', content: heading[2], level: heading[1].length });
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.+)$/);
    if (bullet?.[1]) {
      blocks.push({ type: 'bullet', content: bullet[1] });
      continue;
    }

    const quote = line.match(/^>\s?(.*)$/);
    if (quote?.[1] !== undefined) {
      blocks.push({ type: 'quote', content: quote[1] });
      continue;
    }

    blocks.push({ type: 'paragraph', content: line });
  }

  return (
    <View style={styles.container}>
      {blocks.map((block, index) => {
        const isFirstParagraph = block.type === 'paragraph' && blocks.slice(0, index).every((item) => item.type === 'spacer');

        if (block.type === 'spacer') {
          return <View key={`md-${index}`} style={styles.spacer} />;
        }

        if (block.type === 'heading') {
          return (
            <Text
              key={`md-${index}`}
              style={[
                styles.heading,
                tone === 'dark' ? styles.headingDark : styles.headingLight,
                variant === 'article' ? styles.articleHeading : null,
                block.level === 1 ? styles.h1 : block.level === 2 ? styles.h2 : styles.h3,
                variant === 'article' && block.level === 1 ? styles.articleH1 : null,
                variant === 'article' && block.level === 2 ? styles.articleH2 : null,
                variant === 'article' && block.level > 2 ? styles.articleH3 : null,
              ]}
            >
              {renderInlineChunks(block.content, onOpenNote)}
            </Text>
          );
        }

        if (block.type === 'bullet') {
          return (
            <View key={`md-${index}`} style={styles.bulletRow}>
              <Text style={[styles.bulletMarker, tone === 'dark' ? styles.bulletMarkerDark : styles.bulletMarkerLight]}>•</Text>
              <Text style={[styles.paragraph, tone === 'dark' ? styles.paragraphDark : styles.paragraphLight, variant === 'article' ? styles.articleParagraph : null]}>
                {renderInlineChunks(block.content, onOpenNote)}
              </Text>
            </View>
          );
        }

        if (block.type === 'quote') {
          return (
            <View key={`md-${index}`} style={[styles.quoteBox, tone === 'dark' ? styles.quoteBoxDark : styles.quoteBoxLight]}>
              <Text style={[styles.quoteText, tone === 'dark' ? styles.quoteTextDark : styles.quoteTextLight]}>{renderInlineChunks(block.content, onOpenNote)}</Text>
            </View>
          );
        }

        if (block.type === 'mermaid') {
          return (
            <MermaidDiagram key={`md-${index}`} code={block.content} />
          );
        }

        if (block.type === 'code') {
          return (
            <View key={`md-${index}`} style={[styles.codeBox, tone === 'dark' ? styles.codeBoxDark : null]}>
              <Text style={styles.codeText}>{block.content}</Text>
            </View>
          );
        }

        return (
          <Fragment key={`md-${index}`}>
            <Text
              style={[
                styles.paragraph,
                tone === 'dark' ? styles.paragraphDark : styles.paragraphLight,
                variant === 'article' ? styles.articleParagraph : null,
                variant === 'article' && isFirstParagraph ? styles.articleLead : null,
              ]}
            >
              {renderInlineChunks(block.content, onOpenNote)}
            </Text>
          </Fragment>
        );
      })}
    </View>
  );
}

function renderInlineChunks(value: string, onOpenNote?: (value: string) => void) {
  const chunks = parseInlineChunks(value);
  return chunks.map((chunk, index) => {
    if (chunk.type === 'text') {
      return <Fragment key={`chunk-${index}`}>{chunk.value}</Fragment>;
    }

    if (chunk.type === 'note-link') {
      return (
        <Text key={`chunk-${index}`} style={styles.linkText} onPress={() => onOpenNote?.(chunk.target)}>
          {chunk.label}
        </Text>
      );
    }

    return (
      <Text key={`chunk-${index}`} style={styles.linkText} onPress={() => { void Linking.openURL(chunk.href); }}>
        {chunk.label}
      </Text>
    );
  });
}

function parseInlineChunks(value: string): InlineChunk[] {
  const pattern = /(\[\[([^\]|#]+?)(?:\|([^\]]+))?\]\]|\[([^\]]+)\]\((https?:\/\/[^)]+)\))/g;
  const chunks: InlineChunk[] = [];
  let lastIndex = 0;

  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      chunks.push({ type: 'text', value: value.slice(lastIndex, index) });
    }

    if (match[2]) {
      const target = match[2].trim();
      const label = (match[3] || target).trim();
      chunks.push({ type: 'note-link', label, target: target.endsWith('.md') ? target : `${target}.md` });
    } else if (match[4] && match[5]) {
      chunks.push({ type: 'url-link', label: match[4], href: match[5] });
    }

    lastIndex = index + match[0].length;
  }

  if (lastIndex < value.length) {
    chunks.push({ type: 'text', value: value.slice(lastIndex) });
  }

  return chunks.length ? chunks : [{ type: 'text', value }];
}

const styles = StyleSheet.create({
  container: {
    gap: 8,
  },
  spacer: {
    height: 6,
  },
  heading: {
    fontWeight: '800',
  },
  headingLight: {
    color: '#1f160c',
  },
  headingDark: {
    color: '#f3f3f3',
  },
  articleHeading: {
    letterSpacing: -0.3,
    marginTop: 2,
  },
  h1: {
    fontSize: 24,
  },
  h2: {
    fontSize: 20,
  },
  h3: {
    fontSize: 17,
  },
  articleH1: {
    fontSize: 34,
    lineHeight: 42,
    fontWeight: '700',
    marginBottom: 6,
  },
  articleH2: {
    fontSize: 24,
    lineHeight: 32,
    marginTop: 12,
    marginBottom: 4,
  },
  articleH3: {
    fontSize: 19,
    lineHeight: 28,
    marginTop: 10,
  },
  paragraph: {
    flex: 1,
    lineHeight: 22,
  },
  paragraphLight: {
    color: '#2d2115',
  },
  paragraphDark: {
    color: '#dddddd',
  },
  articleParagraph: {
    fontSize: 18,
    lineHeight: 30,
    letterSpacing: 0.1,
  },
  articleLead: {
    color: '#f1f1f1',
    fontSize: 20,
    lineHeight: 33,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  bulletMarker: {
    marginTop: 1,
    fontSize: 16,
  },
  bulletMarkerLight: {
    color: '#6f5d49',
  },
  bulletMarkerDark: {
    color: '#d6d6d6',
  },
  quoteBox: {
    borderLeftWidth: 3,
    paddingLeft: 12,
    paddingVertical: 8,
  },
  quoteBoxLight: {
    borderLeftColor: '#c8b49d',
    backgroundColor: '#f7f1e7',
  },
  quoteBoxDark: {
    borderLeftColor: '#7d7d7d',
    backgroundColor: '#171717',
  },
  quoteText: {
    fontStyle: 'italic',
    lineHeight: 21,
  },
  quoteTextLight: {
    color: '#5a4a37',
  },
  quoteTextDark: {
    color: '#c8c8c8',
  },
  codeBox: {
    borderRadius: 12,
    backgroundColor: '#221a13',
    padding: 12,
  },
  codeBoxDark: {
    backgroundColor: '#111111',
    borderWidth: 1,
    borderColor: '#303030',
  },
  codeText: {
    color: '#f4ede2',
    fontFamily: 'monospace',
    fontSize: 12,
    lineHeight: 18,
  },
  linkText: {
    color: '#9bc0ff',
    textDecorationLine: 'underline',
  },
});