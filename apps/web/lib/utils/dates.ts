/** Count calendar nights between two date strings. Slices to YYYY-MM-DD to avoid DST edge cases. */
export function nightsBetween(startStr: string, endStr: string): number {
  const start = new Date(startStr.slice(0, 10));
  const end = new Date(endStr.slice(0, 10));
  return Math.round((end.getTime() - start.getTime()) / 86_400_000);
}

/** Normalize YYYY-MM-DD or ISO string to UTC midnight ISO. */
export function toMidnightISO(dateStr: string): string {
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return `${dateStr}T00:00:00.000Z`;
  }
  return dateStr;
}
