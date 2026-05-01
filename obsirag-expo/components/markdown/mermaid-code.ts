const ASCII_REPLACEMENTS: Record<string, string> = {
  '’': "'",
  '‘': "'",
  '“': '"',
  '”': '"',
  '–': '-',
  '—': '-',
  '…': '...',
  '\u00a0': ' ',
};

function replaceAsciiVariants(value: string) {
  return value.replace(/[’‘“”–—…\u00a0]/g, (character) => ASCII_REPLACEMENTS[character] ?? ' ');
}

export function sanitizeMermaidCode(code: string) {
  const normalized = replaceAsciiVariants((code || '').replace(/\r\n/g, '\n'));

  return normalized
    .split('\n')
    .map((line) => {
      const indentMatch = line.match(/^[ \t]*/);
      const indent = indentMatch?.[0] ?? '';
      const body = line.slice(indent.length);
      const asciiBody = body
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .split('')
        .filter((character) => {
          const codePoint = character.charCodeAt(0);
          return codePoint === 9 || codePoint === 10 || codePoint === 13 || (codePoint >= 32 && codePoint <= 126);
        })
        .join('')
        .replace(/ {2,}-/g, ' -')
        .replace(/- {2,}/g, '- ')
        .trimEnd();

      return `${indent}${asciiBody}`;
    })
    .join('\n')
    .trim();
}

export function normalizeMermaidCode(code: string) {
  return sanitizeMermaidCode(code)
    .replace(/(\][ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))/g, ']\n$2')
    .replace(/(\)[ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))/g, ')\n$2')
    .replace(/(\}[ \t]{2,})([A-Za-z][A-Za-z0-9_]*\s*(?:-->|---|==>|-.->|-\.->))/g, '}\n$2')
    .split('\n')
    .map((line) =>
      line.replace(/\b([A-Za-z][A-Za-z0-9_]*)\[(?!["`])([^\]\n]+)\]/g, (_match, nodeId: string, label: string) => {
        if (!/[():]/.test(label)) {
          return `${nodeId}[${label}]`;
        }

        const escapedLabel = label.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        return `${nodeId}["${escapedLabel}"]`;
      }),
    )
    .join('\n');
}

export function findValidationError(value: string) {
  for (let index = 0; index < value.length; index += 1) {
    const current = value.charCodeAt(index);
    if (current === 9 || current === 10 || current === 13) {
      continue;
    }
    if (current < 32 || current > 126) {
      return 'Caracteres non ASCII detectes';
    }
  }
  return null;
}