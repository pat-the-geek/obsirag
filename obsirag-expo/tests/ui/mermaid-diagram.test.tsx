import { normalizeMermaidCode } from '../../components/markdown/mermaid-diagram';

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
});