const LAST_SEEN_KEY = "last_seen_timestamp";

export function getLastSeenTimestamp(): string | null {
  return localStorage.getItem(LAST_SEEN_KEY);
}

export function setLastSeenTimestamp(timestamp: string): void {
  localStorage.setItem(LAST_SEEN_KEY, timestamp);
}