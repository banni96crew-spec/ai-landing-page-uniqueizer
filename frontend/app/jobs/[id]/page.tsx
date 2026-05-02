import { notFound } from "next/navigation";
import Link from "next/link";

import { JobDetailLoader } from "../../../components/JobDetailLoader";

type PageProps = {
  params: { id: string };
};

export default function JobDetailPage({ params }: PageProps) {
  const jobId = Number(params.id);
  if (!Number.isFinite(jobId) || jobId <= 0) {
    notFound();
  }

  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto w-full max-w-3xl py-12">
        <Link
          href="/dashboard"
          className="inline-flex items-center text-sm text-text-secondary transition-colors hover:text-text-primary"
        >
          ← Back to Dashboard
        </Link>

        <JobDetailLoader jobId={jobId} />
      </div>
    </main>
  );
}
