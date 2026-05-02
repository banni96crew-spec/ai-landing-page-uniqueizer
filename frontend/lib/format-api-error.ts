/** FastAPI may return `detail` as a string, or as Pydantic validation items (`msg`, etc.). */

function messageFromValidationItem(item: unknown): string | null {
  if (typeof item === "string" && item.trim()) {
    return item;
  }
  if (!item || typeof item !== "object") {
    return null;
  }
  const msg = (item as { msg?: unknown }).msg;
  return typeof msg === "string" && msg.trim() ? msg : null;
}

function formatDetailField(detail: unknown): string | null {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (Array.isArray(detail)) {
    const parts = detail
      .map((entry) => messageFromValidationItem(entry))
      .filter((s): s is string => Boolean(s));
    return parts.length > 0 ? parts.join("; ") : null;
  }
  return messageFromValidationItem(detail);
}

export function formatApiErrorPayload(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }
  const record = payload as Record<string, unknown>;
  const fromDetail = formatDetailField(record.detail);
  if (fromDetail) {
    return fromDetail;
  }
  const err = record.error;
  if (typeof err === "string" && err.trim()) {
    return err;
  }
  return fallback;
}
