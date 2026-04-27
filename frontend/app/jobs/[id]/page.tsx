import { notFound } from "next/navigation";

import { DownloadButton } from "../../../components/DownloadButton";
import { LogViewer } from "../../../components/LogViewer";
import { ProgressBar } from "../../../components/ProgressBar";
import type { JobDetailResponse } from "../../../components/types";

type PageProps = {
  params: { id: string };
};

async function fetchJob(jobId: number): Promise<JobDetailResponse> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    throw new Error("Missing required env var: NEXT_PUBLIC_API_URL");
  }

  const res = await fetch(`${apiUrl}/api/jobs/${jobId}`, {
    cache: "no-store",
  });

  if (res.status === 404) {
    notFound();
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch job: ${res.status}`);
  }

  return (await res.json()) as JobDetailResponse;
}

export default async function JobDetailPage({ params }: PageProps) {
  const jobId = Number(params.id);
  if (!Number.isFinite(jobId) || jobId <= 0) {
    notFound();
  }

  const job = await fetchJob(jobId);

  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto w-full max-w-3xl py-12">
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
      </div>
    </main>
  );
}

