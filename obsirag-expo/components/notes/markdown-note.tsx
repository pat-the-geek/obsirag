import { Fragment } from 'react';
import { Linking, ScrollView, StyleSheet, Text, View } from 'react-native';

import { AppTheme, buildAppTheme, scaleFontSize, scaleLineHeight, useAppFontScale, useAppTheme } from '../../theme/app-theme';
import { EntityContext } from '../../types/domain';
import { HttpMarkdownImage } from '../markdown/http-markdown-image';
import { MermaidDiagram } from '../markdown/mermaid-diagram';

type MarkdownNoteProps = {
  markdown: string;
  onOpenNote?: (value: string) => void;
  onOpenTag?: (value: string) => void;
  variant?: 'default' | 'article';
  tone?: 'light' | 'dark';
  theme?: AppTheme;
  entityHighlights?: EntityHighlight[];
};

export type EntityHighlight = Pick<EntityContext, 'value' | 'type'>;

type MarkdownBlock =
  | { type: 'spacer'; content: string }
  | { type: 'heading'; content: string; level: number }
  | { type: 'list-item'; content: string; level: number; ordered: boolean; marker: string }
  | { type: 'quote'; content: string }
  | { type: 'code'; content: string }
  | { type: 'mermaid'; content: string }
  | { type: 'image'; alt: string; src: string }
  | { type: 'table'; headers: string[]; rows: string[][]; aligns: MarkdownTableAlign[]; widths: number[] }
  | { type: 'paragraph'; content: string };

type MarkdownTableAlign = 'left' | 'center' | 'right';

type InlineChunk =
  | { type: 'text'; value: string }
  | { type: 'tag'; value: string }
  | { type: 'note-link'; label: string; target: string }
  | { type: 'url-link'; label: string; href: string }
  | { type: 'strong'; value: string }
  | { type: 'emphasis'; value: string }
  | { type: 'inline-code'; value: string };

export function MarkdownNote({ markdown, onOpenNote, onOpenTag, variant = 'default', tone = 'light', theme: preferredTheme, entityHighlights }: MarkdownNoteProps) {
  const activeTheme = useAppTheme();
  const { scale } = useAppFontScale();
  const theme = preferredTheme ?? (activeTheme.resolvedMode === tone ? activeTheme : buildAppTheme(tone === 'dark' ? 'dark' : 'light'));
  const blocks = parseMarkdownBlocks(markdown);

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
                { color: theme.colors.text },
                variant === 'article' ? styles.articleHeading : null,
                block.level === 1 ? styles.h1 : block.level === 2 ? styles.h2 : styles.h3,
                variant === 'article' && block.level === 1 ? styles.articleH1 : null,
                variant === 'article' && block.level === 2 ? styles.articleH2 : null,
                variant === 'article' && block.level > 2 ? styles.articleH3 : null,
                resolveHeadingScale(block.level, variant, scale),
              ]}
            >
              {renderInlineChunks(block.content, onOpenNote, onOpenTag, theme, tone, entityHighlights)}
            </Text>
          );
        }

        if (block.type === 'list-item') {
          return (
            <View key={`md-${index}`} testID="markdown-list-item" style={[styles.bulletRow, { paddingLeft: block.level * 18 }]}>
              <Text
                style={[
                  styles.bulletMarker,
                  { color: theme.colors.textMuted },
                  { fontSize: scaleFontSize(16, scale) },
                  block.ordered ? styles.orderedMarker : null,
                ]}
              >
                {block.marker}
              </Text>
              <Text style={[styles.paragraph, { color: theme.colors.text }, variant === 'article' ? styles.articleParagraph : null, resolveParagraphScale(variant, scale)]}>
                {renderInlineChunks(block.content, onOpenNote, onOpenTag, theme, tone, entityHighlights)}
              </Text>
            </View>
          );
        }

        if (block.type === 'quote') {
          return (
            <View key={`md-${index}`} style={[styles.quoteBox, { borderLeftColor: theme.colors.quoteBorder, backgroundColor: theme.colors.quoteSurface }]}>
              <Text style={[styles.quoteText, { color: theme.colors.textMuted }, { fontSize: scaleFontSize(14, scale), lineHeight: scaleLineHeight(21, scale) }]}>{renderInlineChunks(block.content, onOpenNote, onOpenTag, theme, tone, entityHighlights)}</Text>
            </View>
          );
        }

        if (block.type === 'image') {
          return <HttpMarkdownImage key={`md-${index}`} alt={block.alt} src={block.src} tone={tone} />;
        }

        if (block.type === 'mermaid') {
          return <MermaidDiagram key={`md-${index}`} code={block.content} tone={tone} />;
        }

        if (block.type === 'table') {
          return (
            <ScrollView
              key={`md-${index}`}
              horizontal
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.tableScrollContent}
              testID="markdown-table"
            >
              <View testID="markdown-table-surface" style={[styles.table, { borderColor: theme.colors.tableBorder, backgroundColor: theme.colors.tableSurface }]}>
                <View style={[styles.tableRow, styles.tableHeaderRow, { borderBottomColor: theme.colors.tableBorder, backgroundColor: theme.colors.tableHeaderSurface }]}>
                  {block.headers.map((cell, cellIndex) => (
                    <View key={`header-${cellIndex}`} style={[styles.tableCell, styles.tableHeaderCell, { width: block.widths[cellIndex] ?? 150 }]}>
                      {renderTableCellLines(cell, {
                        theme,
                        tone,
                        textStyle: [
                          styles.tableHeaderText,
                          { color: theme.colors.text },
                          { fontSize: scaleFontSize(13, scale), lineHeight: scaleLineHeight(18, scale) },
                          block.aligns[cellIndex] === 'center'
                            ? styles.tableTextCenter
                            : block.aligns[cellIndex] === 'right'
                              ? styles.tableTextRight
                              : styles.tableTextLeft,
                        ],
                          ...(onOpenNote ? { onOpenNote } : {}),
                          ...(onOpenTag ? { onOpenTag } : {}),
                          ...(entityHighlights ? { entityHighlights } : {}),
                      })}
                    </View>
                  ))}
                </View>
                {block.rows.map((row, rowIndex) => (
                  <View
                    key={`row-${rowIndex}`}
                    style={[
                      styles.tableRow,
                      rowIndex % 2 === 0 ? styles.tableRowOdd : { backgroundColor: theme.colors.surfaceMuted },
                    ]}
                  >
                    {row.map((cell, cellIndex) => (
                      <View key={`row-${rowIndex}-cell-${cellIndex}`} style={[styles.tableCell, { width: block.widths[cellIndex] ?? 150, borderRightColor: theme.colors.tableBorder }]}> 
                        {renderTableCellLines(cell, {
                          theme,
                          tone,
                          textStyle: [
                            styles.tableCellText,
                            { color: theme.colors.text },
                            { fontSize: scaleFontSize(14, scale), lineHeight: scaleLineHeight(20, scale) },
                            block.aligns[cellIndex] === 'center'
                              ? styles.tableTextCenter
                              : block.aligns[cellIndex] === 'right'
                                ? styles.tableTextRight
                                : styles.tableTextLeft,
                          ],
                                ...(onOpenNote ? { onOpenNote } : {}),
                                ...(onOpenTag ? { onOpenTag } : {}),
                                ...(entityHighlights ? { entityHighlights } : {}),
                        })}
                      </View>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          );
        }

        if (block.type === 'code') {
          return (
            <View key={`md-${index}`} style={[styles.codeBox, { backgroundColor: theme.colors.codeSurface, borderColor: theme.colors.border }, tone === 'dark' ? styles.codeBoxDark : null]}>
              <Text style={[styles.codeText, { color: theme.colors.codeText }, { fontSize: scaleFontSize(12, scale), lineHeight: scaleLineHeight(18, scale) }]}>{block.content}</Text>
            </View>
          );
        }

        return (
          <Fragment key={`md-${index}`}>
            <Text
              style={[
                styles.paragraph,
                { color: theme.colors.text },
                variant === 'article' ? styles.articleParagraph : null,
                variant === 'article' && isFirstParagraph ? styles.articleLead : null,
                resolveParagraphScale(variant, scale),
              ]}
            >
              {renderInlineChunks(block.content, onOpenNote, onOpenTag, theme, tone, entityHighlights)}
            </Text>
          </Fragment>
        );
      })}
    </View>
  );
}

function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const lines = normalizeMarkdownTableBlocks(markdown).split('\n');
  const blocks: MarkdownBlock[] = [];
  let inCode = false;
  let codeFenceLanguage = '';
  let codeBuffer: string[] = [];
  let paragraphBuffer: string[] = [];

  const flushParagraph = () => {
    const content = paragraphBuffer.join(' ').trim();
    if (content) {
      blocks.push({ type: 'paragraph', content });
    }
    paragraphBuffer = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index] ?? '';
    const line = rawLine.replace(/\t/g, '  ');
    if (line.trim().startsWith('```')) {
      if (inCode) {
        flushParagraph();
        const fencedContent = codeBuffer.join('\n');
        if (codeFenceLanguage === 'mermaid') {
          blocks.push({ type: 'mermaid', content: fencedContent });
        } else if (codeFenceLanguage === 'markdown' || codeFenceLanguage === 'md') {
          blocks.push(...parseMarkdownBlocks(fencedContent));
        } else {
          blocks.push({ type: 'code', content: fencedContent });
        }
        codeBuffer = [];
        codeFenceLanguage = '';
      } else {
        flushParagraph();
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
      flushParagraph();
      blocks.push({ type: 'spacer', content: '' });
      continue;
    }

    const nextLine = lines[index + 1]?.replace(/\t/g, '  ');
    if (isMarkdownTableRow(line) && nextLine && isMarkdownTableSeparator(nextLine)) {
      flushParagraph();
      const headers = splitMarkdownTableRow(line);
      const aligns = splitMarkdownTableRow(nextLine).map(parseMarkdownTableAlign);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length) {
        const rowLine = lines[index]?.replace(/\t/g, '  ') ?? '';
        if (!isMarkdownTableRow(rowLine)) {
          index -= 1;
          break;
        }
        rows.push(normalizeMarkdownTableRow(splitMarkdownTableRow(rowLine), headers.length));
        index += 1;
      }
      blocks.push({
        type: 'table',
        headers,
        rows,
        aligns: normalizeMarkdownTableAligns(aligns, headers.length),
        widths: estimateMarkdownTableWidths(headers, rows),
      });
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading?.[1] && heading[2]) {
      flushParagraph();
      blocks.push({ type: 'heading', content: heading[2], level: heading[1].length });
      continue;
    }

    const listItem = line.match(/^(\s*)([-*]|\d+\.)\s+(.+)$/);
    if (listItem?.[2] && listItem[3]) {
      flushParagraph();
      const indent = listItem[1] ?? '';
      const marker = listItem[2];
      blocks.push({
        type: 'list-item',
        content: listItem[3],
        level: Math.floor(indent.replace(/\t/g, '  ').length / 2),
        ordered: /\d+\./.test(marker),
        marker: /\d+\./.test(marker) ? marker : '•',
      });
      continue;
    }

    const quote = line.match(/^>\s?(.*)$/);
    if (quote?.[1] !== undefined) {
      flushParagraph();
      blocks.push({ type: 'quote', content: quote[1] });
      continue;
    }

    const image = line.match(/^!\[([^\]]*)\]\((https?:\/\/[^\s)]+)(?:\s+"[^"]*")?\)$/i);
    if (image?.[1] !== undefined && image[2]) {
      flushParagraph();
      blocks.push({ type: 'image', alt: image[1], src: image[2] });
      continue;
    }

    paragraphBuffer.push(line.trim());
  }

  if (inCode) {
    const fencedContent = codeBuffer.join('\n');
    if (codeFenceLanguage === 'mermaid') {
      blocks.push({ type: 'mermaid', content: fencedContent });
    } else {
      blocks.push({ type: 'code', content: fencedContent });
    }
  }

  flushParagraph();
  return blocks;
}

function isMarkdownTableRow(line: string): boolean {
  const trimmed = line.trim();
  if (trimmed.length < 3 || !trimmed.includes('|')) {
    return false;
  }
  const cells = trimmed.replace(/^\|/, '').replace(/\|$/, '').split('|');
  return cells.some((cell) => cell.trim().length > 0);
}

function normalizeMarkdownTableBlocks(markdown: string): string {
  const lines = markdown.split('\n');
  const normalized: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? '';
    const nextLine = lines[index + 1] ?? '';
    if (isMarkdownTableRow(line) && isMarkdownTableSeparator(nextLine)) {
      const headers = splitMarkdownTableRow(line);
      const width = Math.max(headers.length, 1);
      normalized.push(toMarkdownTableRow(normalizeMarkdownTableRow(headers, width)));
      normalized.push(toMarkdownTableRow(normalizeMarkdownTableRow(splitMarkdownTableRow(nextLine), width)));
      index += 2;

      while (index < lines.length) {
        const rowLine = lines[index] ?? '';
        if (!isMarkdownTableRow(rowLine)) {
          index -= 1;
          break;
        }
        normalized.push(toMarkdownTableRow(normalizeMarkdownTableRow(splitMarkdownTableRow(rowLine), width)));
        index += 1;
      }
      continue;
    }

    normalized.push(line);
  }

  return normalized.join('\n');
}

function isMarkdownTableSeparator(line: string): boolean {
  const trimmed = line.trim();
  return /^\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?$/.test(trimmed);
}

function splitMarkdownTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim());
}

function normalizeMarkdownTableRow(cells: string[], width: number): string[] {
  if (cells.length === width) {
    return cells;
  }
  if (cells.length > width) {
    return cells.slice(0, width);
  }
  return [...cells, ...Array.from({ length: width - cells.length }, () => '')];
}

function toMarkdownTableRow(cells: string[]): string {
  return `| ${cells.map((cell) => cell.trim()).join(' | ')} |`;
}

function normalizeMarkdownTableCellContent(value: string): string {
  return value.replace(/<br\s*\/?>/gi, '\n').replace(/\\n/g, '\n');
}

function parseMarkdownTableAlign(cell: string): MarkdownTableAlign {
  const trimmed = cell.trim();
  if (trimmed.startsWith(':') && trimmed.endsWith(':')) {
    return 'center';
  }
  if (trimmed.endsWith(':')) {
    return 'right';
  }
  return 'left';
}

function normalizeMarkdownTableAligns(aligns: MarkdownTableAlign[], width: number): MarkdownTableAlign[] {
  if (aligns.length >= width) {
    return aligns.slice(0, width);
  }
  return [...aligns, ...Array.from({ length: width - aligns.length }, () => 'left' as const)];
}

function estimateMarkdownTableWidths(headers: string[], rows: string[][]): number[] {
  const rawWidths = headers.map((header, index) => {
    const values = [header, ...rows.map((row) => row[index] ?? '')];
    const maxChars = values.reduce((current, value) => {
      const longestLine = normalizeMarkdownTableCellContent(value)
        .split('\n')
        .reduce((lineMax, line) => Math.max(lineMax, line.trim().length), 0);
      return Math.max(current, longestLine);
    }, 0);
    return Math.min(420, Math.max(132, Math.round(Math.sqrt(Math.max(1, maxChars)) * 28 + 72)));
  });

  const maxTotalWidth = 920;
  const totalWidth = rawWidths.reduce((sum, width) => sum + width, 0);
  if (totalWidth <= maxTotalWidth) {
    return rawWidths;
  }

  const minWidth = 132;
  const shrinkable = rawWidths.map((width) => Math.max(0, width - minWidth));
  const shrinkableTotal = shrinkable.reduce((sum, width) => sum + width, 0);
  if (shrinkableTotal <= 0) {
    return rawWidths;
  }

  const overflow = totalWidth - maxTotalWidth;
  return rawWidths.map((width, index) => {
    const proportionalShrink = ((shrinkable[index] ?? 0) / shrinkableTotal) * overflow;
    return Math.max(minWidth, Math.round(width - proportionalShrink));
  });
}

function renderTableCellLines(
  value: string,
  options: {
    onOpenNote?: (value: string) => void;
    onOpenTag?: (value: string) => void;
    textStyle: object | object[];
    theme: AppTheme;
    tone: 'light' | 'dark';
    entityHighlights?: EntityHighlight[];
  },
) {
  const lines = normalizeMarkdownTableCellContent(value).split('\n');
  return (
    <View testID={lines.length > 1 ? 'markdown-table-cell-multiline' : undefined} style={styles.tableCellInner}>
      {lines.map((line, index) => (
        <Text key={`table-line-${index}`} style={[options.textStyle, index > 0 ? styles.tableCellLineBreak : null]}>
          {renderInlineChunks(line, options.onOpenNote, options.onOpenTag, options.theme, options.tone, options.entityHighlights)}
        </Text>
      ))}
    </View>
  );
}

function resolveHeadingScale(level: number, variant: MarkdownNoteProps['variant'], scale: number) {
  if (variant === 'article') {
    if (level === 1) {
      return { fontSize: scaleFontSize(34, scale), lineHeight: scaleLineHeight(42, scale) };
    }
    if (level === 2) {
      return { fontSize: scaleFontSize(24, scale), lineHeight: scaleLineHeight(32, scale) };
    }
    return { fontSize: scaleFontSize(19, scale), lineHeight: scaleLineHeight(28, scale) };
  }

  if (level === 1) {
    return { fontSize: scaleFontSize(24, scale) };
  }
  if (level === 2) {
    return { fontSize: scaleFontSize(20, scale) };
  }
  return { fontSize: scaleFontSize(17, scale) };
}

function resolveParagraphScale(variant: MarkdownNoteProps['variant'], scale: number) {
  if (variant === 'article') {
    return { fontSize: scaleFontSize(15, scale), lineHeight: scaleLineHeight(22, scale) };
  }
  return { fontSize: scaleFontSize(14, scale), lineHeight: scaleLineHeight(22, scale) };
}

export function renderEntityHighlightedText(
  value: string,
  tone: 'light' | 'dark' = 'light',
  entityHighlights?: EntityHighlight[],
  baseTextStyle?: object | object[],
  keyPrefix = 'entity-highlight',
  theme?: AppTheme,
) {
  const resolvedTheme = theme && theme.resolvedMode === tone ? theme : buildAppTheme(tone === 'dark' ? 'dark' : 'light');
  const segments = splitEntityHighlightSegments(value, entityHighlights);

  return segments.map((segment, index) => {
    const key = `${keyPrefix}-${index}`;
    if (segment.type === 'text') {
      if (baseTextStyle) {
        return (
          <Text key={key} style={baseTextStyle}>
            {segment.value}
          </Text>
        );
      }
      return <Fragment key={key}>{segment.value}</Fragment>;
    }

    return (
      <Text
        key={key}
        testID="markdown-inline-entity-highlight"
        style={[baseTextStyle, styles.entityHighlightBase, getEntityHighlightStyle(segment.entityType, resolvedTheme)]}
      >
        {segment.value}
      </Text>
    );
  });
}

function renderInlineChunks(
  value: string,
  onOpenNote?: (value: string) => void,
  onOpenTag?: (value: string) => void,
  theme?: AppTheme,
  tone: 'light' | 'dark' = 'light',
  entityHighlights?: EntityHighlight[],
) {
  const resolvedTheme = theme && theme.resolvedMode === tone ? theme : buildAppTheme(tone === 'dark' ? 'dark' : 'light');
  const chunks = parseInlineChunks(value);
  return chunks.map((chunk, index) => {
    if (chunk.type === 'text') {
      return <Fragment key={`chunk-${index}`}>{renderEntityHighlightedText(chunk.value, tone, entityHighlights, undefined, `chunk-${index}`, resolvedTheme)}</Fragment>;
    }

    if (chunk.type === 'tag') {
      return (
        <Text
          key={`chunk-${index}`}
          testID="markdown-inline-tag"
          style={[styles.tagText, { color: resolvedTheme.colors.tagText, backgroundColor: resolvedTheme.colors.tagSurface }]}
          onPress={onOpenTag ? () => onOpenTag(chunk.value.slice(1)) : undefined}
        >
          {chunk.value}
        </Text>
      );
    }

    if (chunk.type === 'strong') {
      return <Fragment key={`chunk-${index}`}>{renderEntityHighlightedText(chunk.value, tone, entityHighlights, styles.strongText, `chunk-${index}`, resolvedTheme)}</Fragment>;
    }

    if (chunk.type === 'emphasis') {
      return <Fragment key={`chunk-${index}`}>{renderEntityHighlightedText(chunk.value, tone, entityHighlights, styles.emphasisText, `chunk-${index}`, resolvedTheme)}</Fragment>;
    }

    if (chunk.type === 'inline-code') {
      return (
        <Text key={`chunk-${index}`} style={[styles.inlineCodeText, { color: resolvedTheme.colors.codeText, backgroundColor: resolvedTheme.colors.codeSurface }]}>
          {chunk.value}
        </Text>
      );
    }

    if (chunk.type === 'note-link') {
      return (
        <Text key={`chunk-${index}`} style={[styles.linkText, { color: resolvedTheme.colors.link }]} onPress={() => onOpenNote?.(chunk.target)}>
          {chunk.label}
        </Text>
      );
    }

    return (
      <Text key={`chunk-${index}`} style={[styles.linkText, { color: resolvedTheme.colors.link }]} onPress={() => { void Linking.openURL(chunk.href); }}>
        {chunk.label}
      </Text>
    );
  });
}

function parseInlineChunks(value: string): InlineChunk[] {
  const pattern = /(\[\[([^\]|#]+?)(?:\|([^\]]+))?\]\]|\[([^\]]+)\]\((https?:\/\/[^)]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|`([^`]+)`|\*([^*]+)\*|_([^_]+)_)/g;
  const chunks: InlineChunk[] = [];
  let lastIndex = 0;

  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    if (index > lastIndex) {
      chunks.push(...splitInlineTags(value.slice(lastIndex, index)));
    }

    if (match[2]) {
      const target = match[2].trim();
      const label = (match[3] || target).trim();
      chunks.push({ type: 'note-link', label, target: target.endsWith('.md') ? target : `${target}.md` });
    } else if (match[4] && match[5]) {
      chunks.push({ type: 'url-link', label: match[4], href: match[5] });
    } else if (match[6] || match[7]) {
      chunks.push({ type: 'strong', value: String(match[6] || match[7]).trim() });
    } else if (match[8]) {
      chunks.push({ type: 'inline-code', value: match[8] });
    } else if (match[9] || match[10]) {
      chunks.push({ type: 'emphasis', value: String(match[9] || match[10]).trim() });
    }

    lastIndex = index + match[0].length;
  }

  if (lastIndex < value.length) {
    chunks.push(...splitInlineTags(value.slice(lastIndex)));
  }

  return chunks.length ? chunks : [{ type: 'text', value }];
}

type EntityTextSegment =
  | { type: 'text'; value: string }
  | { type: 'entity'; value: string; entityType: string };

function splitEntityHighlightSegments(value: string, entityHighlights?: EntityHighlight[]): EntityTextSegment[] {
  const candidates = normalizeEntityHighlights(entityHighlights);
  if (!value || !candidates.length) {
    return [{ type: 'text', value }];
  }

  const segments: EntityTextSegment[] = [];
  const lowered = value.toLocaleLowerCase('fr');
  let cursor = 0;

  while (cursor < value.length) {
    const match = findEntityMatchAt(value, lowered, cursor, candidates);
    if (!match) {
      const nextCursor = cursor + 1;
      const previous = segments[segments.length - 1];
      const char = value.slice(cursor, nextCursor);
      if (previous?.type === 'text') {
        previous.value += char;
      } else {
        segments.push({ type: 'text', value: char });
      }
      cursor = nextCursor;
      continue;
    }

    if (match.start > cursor) {
      segments.push({ type: 'text', value: value.slice(cursor, match.start) });
    }

    segments.push({ type: 'entity', value: value.slice(match.start, match.end), entityType: match.entity.type });
    cursor = match.end;
  }

  return segments.length ? segments : [{ type: 'text', value }];
}

function normalizeEntityHighlights(entityHighlights?: EntityHighlight[]) {
  return (entityHighlights ?? [])
    .map((entity) => ({ ...entity, value: entity.value.trim() }))
    .filter((entity) => entity.value.length > 1)
    .sort((left, right) => right.value.length - left.value.length);
}

function findEntityMatchAt(
  rawValue: string,
  loweredValue: string,
  cursor: number,
  entityHighlights: EntityHighlight[],
): { start: number; end: number; entity: EntityHighlight } | null {
  for (const entity of entityHighlights) {
    const loweredEntity = entity.value.toLocaleLowerCase('fr');
    if (!loweredValue.startsWith(loweredEntity, cursor)) {
      continue;
    }

    const start = cursor;
    const end = cursor + entity.value.length;
    if (!isWordBoundary(rawValue, start - 1) || !isWordBoundary(rawValue, end)) {
      continue;
    }
    return { start, end, entity };
  }

  return null;
}

function isWordBoundary(value: string, index: number) {
  if (index < 0 || index >= value.length) {
    return true;
  }
  return !/[\p{L}\p{N}_]/u.test(value[index] ?? '');
}

function getEntityHighlightStyle(entityType: string, theme: AppTheme) {
  const normalized = entityType.trim().toLocaleLowerCase('fr');

  if (normalized.includes('person')) {
    return { color: theme.colors.entityPersonText, backgroundColor: theme.colors.entityPersonSurface };
  }
  if (normalized.includes('org')) {
    return { color: theme.colors.entityOrganizationText, backgroundColor: theme.colors.entityOrganizationSurface };
  }
  if (normalized.includes('loc') || normalized.includes('place') || normalized.includes('geo')) {
    return { color: theme.colors.entityLocationText, backgroundColor: theme.colors.entityLocationSurface };
  }
  if (normalized.includes('date') || normalized.includes('time')) {
    return { color: theme.colors.entityTemporalText, backgroundColor: theme.colors.entityTemporalSurface };
  }

  return { color: theme.colors.entityConceptText, backgroundColor: theme.colors.entityConceptSurface };
}

function splitInlineTags(value: string): InlineChunk[] {
  const chunks: InlineChunk[] = [];
  const pattern = /#([\p{L}\p{N}_-]+)/gu;
  let lastIndex = 0;

  for (const match of value.matchAll(pattern)) {
    const index = match.index ?? 0;
    const previousChar = index > 0 ? value[index - 1] : '';
    if (previousChar && /[\p{L}\p{N}_/]/u.test(previousChar)) {
      continue;
    }

    if (index > lastIndex) {
      chunks.push({ type: 'text', value: value.slice(lastIndex, index) });
    }

    chunks.push({ type: 'tag', value: match[0] });
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
    fontSize: 15,
    lineHeight: 22,
    letterSpacing: 0.1,
  },
  articleLead: {
    fontSize: 15,
    lineHeight: 22,
  },
  bulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
  },
  bulletMarker: {
    marginTop: 1,
    fontSize: 16,
    width: 28,
    flexShrink: 0,
  },
  orderedMarker: {
    fontSize: 14,
    fontWeight: '700',
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
  strongText: {
    fontWeight: '800',
  },
  emphasisText: {
    fontStyle: 'italic',
  },
  inlineCodeText: {
    fontFamily: 'monospace',
    fontSize: 12,
    color: '#f4ede2',
    backgroundColor: '#221a13',
    borderRadius: 6,
    overflow: 'hidden',
    paddingHorizontal: 5,
    paddingVertical: 2,
  },
  tagText: {
    borderRadius: 999,
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 2,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: '700',
  },
  tagTextLight: {
    color: '#17324a',
    backgroundColor: '#d8ebff',
  },
  tagTextDark: {
    color: '#e7f2ff',
    backgroundColor: '#27425c',
  },
  entityHighlightBase: {
    borderRadius: 6,
    overflow: 'hidden',
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  entityHighlightPersonLight: {
    color: '#163a56',
    backgroundColor: '#cfe8ff',
  },
  entityHighlightPersonDark: {
    color: '#f2f8ff',
    backgroundColor: '#315a7c',
  },
  entityHighlightOrganizationLight: {
    color: '#5c3900',
    backgroundColor: '#ffe4b8',
  },
  entityHighlightOrganizationDark: {
    color: '#fff6e9',
    backgroundColor: '#7a5626',
  },
  entityHighlightLocationLight: {
    color: '#18472a',
    backgroundColor: '#d5f1cf',
  },
  entityHighlightLocationDark: {
    color: '#eefbe8',
    backgroundColor: '#38684a',
  },
  entityHighlightTemporalLight: {
    color: '#5a2d16',
    backgroundColor: '#ffd7c4',
  },
  entityHighlightTemporalDark: {
    color: '#fff1ea',
    backgroundColor: '#7d4a34',
  },
  entityHighlightConceptLight: {
    color: '#3c245d',
    backgroundColor: '#e8dafb',
  },
  entityHighlightConceptDark: {
    color: '#f6efff',
    backgroundColor: '#624784',
  },
  tableScrollContent: {
    paddingVertical: 4,
  },
  table: {
    minWidth: 460,
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
  },
  tableRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  tableHeaderRow: {
    borderBottomWidth: 1,
  },
  tableRowOdd: {
    backgroundColor: 'transparent',
  },
  tableCell: {
    minWidth: 132,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRightWidth: 1,
  },
  tableHeaderCell: {
    justifyContent: 'center',
  },
  tableCellInner: {
    gap: 4,
  },
  tableCellLineBreak: {
    marginTop: 2,
  },
  tableHeaderText: {
    fontSize: 13,
    fontWeight: '800',
    lineHeight: 18,
  },
  tableHeaderTextLight: {
    color: '#2d2115',
  },
  tableHeaderTextDark: {
    color: '#f2f2f2',
  },
  tableCellText: {
    fontSize: 14,
    lineHeight: 20,
  },
  tableCellTextLight: {
    color: '#3a2c1f',
  },
  tableCellTextDark: {
    color: '#dddddd',
  },
  tableTextLeft: {
    textAlign: 'left',
  },
  tableTextCenter: {
    textAlign: 'center',
  },
  tableTextRight: {
    textAlign: 'right',
  },
});