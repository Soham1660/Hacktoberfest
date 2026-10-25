const DAY_MS = 24 * 60 * 60 * 1000;

export function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

/** YYYY-MM-DD in UTC. */
export function formatDate(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

/** YYYY-MM-DD HH:mm UTC. */
export function formatTimestamp(ms: number): string {
  const d = new Date(ms);
  return `${formatDate(ms)} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())} UTC`;
}

export function addDays(ms: number, days: number): number {
  return ms + days * DAY_MS;
}
