export interface IcsSlot {
  id: string;
  dayNumber: number;
  sortOrder: number;
  startTime: string | null;
  endTime: string | null;
  durationMinutes: number | null;
  activityNode: {
    name: string;
    category: string;
  } | null;
}

export interface IcsTripData {
  id: string;
  destination: string;
  city: string;
  timezone: string;
  startDate: string;
  endDate: string;
  slots: IcsSlot[];
}

function escapeIcsText(text: string): string {
  return text
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\n/g, '\\n');
}

/**
 * Fold lines longer than 75 octets per RFC 5545 §3.1.
 * Continuation lines begin with a single WSP character (SPACE).
 */
function foldLine(line: string): string {
  // RFC 5545 uses octets, but for ASCII-safe content byte length === char length.
  // We fold at 75 characters, inserting CRLF + SPACE.
  const LIMIT = 75;
  if (line.length <= LIMIT) return line;

  let result = '';
  let remaining = line;

  // First chunk: 75 chars
  result += remaining.slice(0, LIMIT);
  remaining = remaining.slice(LIMIT);

  // Subsequent chunks: 74 chars (1 char consumed by leading SPACE)
  while (remaining.length > 0) {
    result += '\r\n ';
    result += remaining.slice(0, 74);
    remaining = remaining.slice(74);
  }

  return result;
}

/** Format a Date as YYYYMMDDTHHMMSSZ (UTC) */
function formatUtcStamp(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return (
    String(date.getUTCFullYear()) +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    'T' +
    pad(date.getUTCHours()) +
    pad(date.getUTCMinutes()) +
    pad(date.getUTCSeconds()) +
    'Z'
  );
}

/**
 * Format a local datetime as YYYYMMDDTHHMMSS (no Z — used with TZID param).
 * `dateStr` is ISO date (YYYY-MM-DD), `timeStr` is HH:MM.
 */
function formatLocalDateTime(dateStr: string, timeStr: string): string {
  // dateStr: "2026-03-15", timeStr: "09:00"
  const [year, month, day] = dateStr.split('-');
  const [hour, minute] = timeStr.split(':');
  const pad = (s: string) => s.padStart(2, '0');
  return `${year}${pad(month)}${pad(day)}T${pad(hour)}${pad(minute)}00`;
}

/** Add `days` days to an ISO date string (YYYY-MM-DD) and return YYYY-MM-DD */
function addDays(isoDate: string, days: number): string {
  // Parse as UTC noon to avoid DST edge cases
  const d = new Date(`${isoDate}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** Add `minutes` to a HH:MM string and return HH:MM (no overflow past midnight guard — 90 min max) */
function addMinutesToTime(timeStr: string, minutes: number): string {
  const [h, m] = timeStr.split(':').map(Number);
  const total = h * 60 + m + minutes;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(Math.floor(total / 60) % 24)}:${pad(total % 60)}`;
}

const SORT_ORDER_DEFAULTS: Record<number, string> = {
  1: '09:00',
  2: '12:00',
  3: '15:00',
};

function defaultTimeForSortOrder(sortOrder: number): string {
  return SORT_ORDER_DEFAULTS[sortOrder] ?? '18:00';
}

export function generateIcsCalendar(trip: IcsTripData): string {
  const timezone = trip.timezone || 'UTC';
  const now = formatUtcStamp(new Date());

  const lines: string[] = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Overplanned//Trip Calendar//EN',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    `X-WR-CALNAME:${escapeIcsText(trip.destination)}`,
    `X-WR-TIMEZONE:${timezone}`,
  ];

  for (const slot of trip.slots) {
    // Skip slots with no activity data
    if (!slot.activityNode) continue;

    const baseDate = addDays(trip.startDate, slot.dayNumber - 1);
    const startTimeStr = slot.startTime
      ? // slot.startTime may be a full ISO datetime or just HH:MM
        slot.startTime.includes('T')
        ? slot.startTime.split('T')[1].slice(0, 5)
        : slot.startTime.slice(0, 5)
      : defaultTimeForSortOrder(slot.sortOrder);

    const durationMins = slot.durationMinutes ?? 90;
    const endTimeStr = addMinutesToTime(startTimeStr, durationMins);

    const dtStart = formatLocalDateTime(baseDate, startTimeStr);
    const dtEnd = formatLocalDateTime(baseDate, endTimeStr);

    const summary = escapeIcsText(slot.activityNode.name);
    const description = escapeIcsText(slot.activityNode.category);

    lines.push('BEGIN:VEVENT');
    lines.push(foldLine(`UID:${slot.id}@overplanned.app`));
    lines.push(foldLine(`DTSTAMP:${now}`));
    lines.push(foldLine(`DTSTART;TZID=${timezone}:${dtStart}`));
    lines.push(foldLine(`DTEND;TZID=${timezone}:${dtEnd}`));
    lines.push(foldLine(`SUMMARY:${summary}`));
    lines.push(foldLine(`DESCRIPTION:${description}`));
    lines.push('END:VEVENT');
  }

  lines.push('END:VCALENDAR');

  return lines.join('\r\n') + '\r\n';
}

export function downloadIcsFile(trip: IcsTripData): void {
  const icsContent = generateIcsCalendar(trip);
  const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${trip.destination.replace(/[^a-zA-Z0-9]/g, '-')}.ics`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
