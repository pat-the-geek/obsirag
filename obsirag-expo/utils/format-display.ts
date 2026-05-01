export function formatMetadataDate(value?: string | null): string {
  if (!value) {
    return '';
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString('fr-FR');
}

export function formatSizeBytes(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return '';
  }

  const formatCompact = (numberValue: number) => {
    const rounded = Number(numberValue.toFixed(1));
    return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
  };

  if (value < 1024) {
    return `${Math.round(value)} B`;
  }

  const kib = value / 1024;
  if (kib < 1024) {
    return `${formatCompact(kib)} ko`;
  }

  const mib = kib / 1024;
  return `${formatCompact(mib)} Mo`;
}

export function joinMetadataParts(parts: Array<string | null | undefined>): string {
  return parts
    .map((part) => (part ?? '').trim())
    .filter((part) => Boolean(part))
    .join(' · ');
}
