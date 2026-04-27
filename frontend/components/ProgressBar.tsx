"use client";

import { motion } from "framer-motion";

import type { JobStatus } from "./types";

const STATUS_LABELS: Record<JobStatus, string> = {
  pending: "Waiting in queue",
  running: "Processing...",
  done: "Completed",
  failed: "Failed",
};

export function ProgressBar({
  status,
  progressPct,
}: {
  status: JobStatus;
  progressPct: number;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(progressPct)));

  return (
    <div>
      <div className="h-1 overflow-hidden rounded-full bg-border">
        <motion.div
          className="h-full rounded-full bg-accent"
          animate={{ width: `${clamped}%` }}
          transition={{ duration: 0.8, ease: "easeInOut" }}
        />
      </div>
      <div className="mt-2 text-xs text-text-secondary">
        Stage: {STATUS_LABELS[status]} ({clamped}%)
      </div>
    </div>
  );
}

