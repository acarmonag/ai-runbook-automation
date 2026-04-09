import { formatDistanceToNow, parseISO } from "date-fns";

export function formatDuration(startedAt: string, resolvedAt?: string): string {
  const start = parseISO(startedAt);
  const end = resolvedAt ? parseISO(resolvedAt) : new Date();
  const ms = end.getTime() - start.getTime();

  if (ms < 60_000) return `${Math.round(ms / 1_000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${(ms / 3_600_000).toFixed(1)}h`;
}

export function formatRelative(iso: string): string {
  return formatDistanceToNow(parseISO(iso), { addSuffix: true });
}

export function formatTimestamp(iso: string): string {
  return parseISO(iso).toLocaleString();
}

export function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max) + "…" : str;
}
