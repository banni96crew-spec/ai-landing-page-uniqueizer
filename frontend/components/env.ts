function stripTrailingSlash(url: string): string {
  return url.replace(/\/$/, "");
}

/** WebSocket base (no path). Prefer NEXT_PUBLIC_WS_URL; else same hostname as UI :8000. */
export function getResolvedWsBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL?.trim();
  if (explicit) {
    return stripTrailingSlash(explicit);
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.hostname}:8000`;
  }
  return "ws://127.0.0.1:8000";
}
