"use client";

import Link from "next/link";

import { DownloadButton } from "./DownloadButton";
import { JobStatusBadge } from "./JobStatusBadge";
import type { JobResponse } from "./types";

export function JobCard({ job }: { job: JobResponse }) {
  return (
    <Link
      href={`/jobs/${job.id}`}
      className="block rounded-card border border-border bg-bg-secondary p-4 transition-colors duration-200 hover:border-accent/50"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <div className="truncate font-mono text-sm text-text-primary">
            {job.target_url}
          </div>
          <div className="mt-1 text-xs text-text-secondary">{job.created_at}</div>
        </div>

        <div className="flex items-center gap-3">
          <JobStatusBadge status={job.status} />
          {job.status === "done" ? <DownloadButton jobId={job.id} /> : null}
        </div>
      </div>
    </Link>
  );
}

