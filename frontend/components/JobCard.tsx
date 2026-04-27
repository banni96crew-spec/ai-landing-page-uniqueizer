"use client";

import Link from "next/link";

import { DownloadButton } from "./DownloadButton";
import { JobStatusBadge } from "./JobStatusBadge";
import type { JobResponse } from "./types";

function formatCreatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function JobCard({ job }: { job: JobResponse }) {
  return (
    <div className="rounded-card border border-border bg-bg-secondary p-4 transition-colors duration-200 hover:border-accent/50">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <Link
            href={`/jobs/${job.id}`}
            className="block truncate font-mono text-sm text-text-primary hover:text-accent transition-colors"
          >
            {job.target_url}
          </Link>
          <div className="mt-1 text-xs text-text-secondary">
            {formatCreatedAt(job.created_at)}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <JobStatusBadge status={job.status} />
          {job.status === "done" ? <DownloadButton jobId={job.id} /> : null}
        </div>
      </div>
    </div>
  );
}

