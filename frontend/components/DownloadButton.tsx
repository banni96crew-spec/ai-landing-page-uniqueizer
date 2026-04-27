"use client";

import { useMemo } from "react";

import { getRequiredPublicEnv } from "./env";

export function DownloadButton({ jobId }: { jobId: number }) {
  const apiUrl = useMemo(() => getRequiredPublicEnv("NEXT_PUBLIC_API_URL"), []);
  const href = `${apiUrl}/api/artifacts/${jobId}/download`;

  return (
    <a
      href={href}
      className="inline-flex items-center justify-center rounded-card border border-border bg-bg-primary px-4 py-2 text-sm font-semibold text-text-primary transition-colors hover:border-accent/50"
    >
      Download ZIP
    </a>
  );
}

