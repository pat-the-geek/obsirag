export function formatMetadataDate(value?: string): string | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return new Intl.DateTimeFormat('fr-CH', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed);
}

export function formatSizeBytes(sizeBytes?: number): string | null {
  if (!Number.isFinite(sizeBytes) || sizeBytes === undefined || sizeBytes < 0) {
    return null;
  }

  const kiloBytes = sizeBytes / 1024;
  const rounded = Math.round(kiloBytes * 10) / 10;
  const displayValue = sizeBytes > 0 ? Math.max(0.1, rounded) : 0;
  return `${Number.isInteger(displayValue) ? displayValue : displayValue.toFixed(1)} ko`;
}

export function joinMetadataParts(parts: Array<string | null | undefined>): string {
  return parts.filter((part): part is string => Boolean(part)).join(' · ');
}