"use client";

import { useMemo } from "react";

function stripTrailingSlash(url: string): string {
  return url.replace(/\/$/, "");
}

export function DownloadButton({ jobId }: { jobId: number }) {
  const href = useMemo(() => {
    const explicit = process.env.NEXT_PUBLIC_API_URL?.trim();
    if (explicit) {
      return `${stripTrailingSlash(explicit)}/api/artifacts/${jobId}/download`;
    }
    return `/api/artifacts/${jobId}/download`;
  }, [jobId]);

  return (
    <a
      href={href}
      className="inline-flex items-center justify-center rounded-card border border-border bg-bg-primary px-4 py-2 text-sm font-semibold text-text-primary transition-colors hover:border-accent/50"
    >
      Download ZIP
    </a>
  );
}

