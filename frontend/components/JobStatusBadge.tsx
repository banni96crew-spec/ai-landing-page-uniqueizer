import type { JobStatus } from "./types";

const STATUS_CONFIG: Record<
  JobStatus,
  { label: string; className: string }
> = {
  pending: { label: "Queued", className: "text-text-secondary bg-border" },
  running: { label: "Processing", className: "text-warn bg-warn/10" },
  done: { label: "Done", className: "text-success bg-success/10" },
  failed: { label: "Failed", className: "text-error bg-error/10" },
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const cfg = STATUS_CONFIG[status];
  return (
    <span className={`rounded-md px-2 py-1 text-xs font-medium ${cfg.className}`}>
      {cfg.label}
    </span>
  );
}

