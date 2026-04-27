"use client";

import { useEffect, useMemo, useState } from "react";

import { DownloadButton } from "./DownloadButton";
import { getRequiredPublicEnv } from "./env";
import { LogViewer } from "./LogViewer";
import { ProgressBar } from "./ProgressBar";
import type { JobDetailResponse } from "./types";

export function JobDetailClient({
  initialJob,
}: {
  initialJob: JobDetailResponse;
}) {
  const apiUrl = useMemo(() => getRequiredPublicEnv("NEXT_PUBLIC_API_URL"), []);
  const [job, setJob] = useState<JobDetailResponse>(initialJob);

  useEffect(() => {
    setJob(initialJob);
  }, [initialJob]);

  useEffect(() => {
    if (job.status === "done" || job.status === "failed") return;

    let alive = true;
    const interval = window.setInterval(async () => {
      try {
        const res = await fetch(`${apiUrl}/api/jobs/${job.id}`, {
          method: "GET",
          cache: "no-store",
        });
        if (!res.ok) return;
        const next = (await res.json()) as JobDetailResponse;
        if (!alive) return;
        setJob(next);
      } catch {
        // ignore polling errors
      }
    }, 2000);

    return () => {
      alive = false;
      window.clearInterval(interval);
    };
  }, [apiUrl, job.id, job.status]);

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-card border border-border bg-bg-secondary p-5">
        <div className="flex flex-col gap-2">
          <div className="text-xs text-text-secondary">Target URL</div>
          <div className="truncate font-mono text-sm text-text-primary">
            {job.target_url}
          </div>
        </div>

        <div className="mt-6">
          <ProgressBar status={job.status} progressPct={job.progress_pct} />
        </div>

        {job.status === "done" ? (
          <div className="mt-6">
            <DownloadButton jobId={job.id} />
          </div>
        ) : null}
      </div>

      <LogViewer jobId={job.id} />
    </div>
  );
}

