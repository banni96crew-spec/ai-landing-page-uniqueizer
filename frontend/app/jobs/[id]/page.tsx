import { notFound } from "next/navigation";

import { JobDetailClient } from "../../../components/JobDetailClient";
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
        <JobDetailClient initialJob={job} />
      </div>
    </main>
  );
}

