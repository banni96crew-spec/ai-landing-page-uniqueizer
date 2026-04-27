"use client";

import { useEffect, useState } from "react";

import { getRequiredPublicEnv } from "./env";
import { JobCard } from "./JobCard";
import { SkeletonCard } from "./SkeletonCard";
import type { JobResponse } from "./types";

export function JobList() {
  const [jobs, setJobs] = useState<JobResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    const apiUrl = getRequiredPublicEnv("NEXT_PUBLIC_API_URL");

    async function load() {
      try {
        const res = await fetch(`${apiUrl}/api/jobs?limit=20&offset=0`, {
          method: "GET",
        });

        if (!res.ok) {
          setError(`Error ${res.status}`);
          setJobs([]);
          return;
        }

        const data = (await res.json()) as JobResponse[];
        if (!isMounted) return;
        setJobs(data);
      } catch {
        if (!isMounted) return;
        setError("Network error");
        setJobs([]);
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <section className="mx-auto w-full max-w-2xl pb-24">
      <h2 className="text-lg font-medium text-text-primary">Recent jobs</h2>

      <div className="mt-4 flex flex-col gap-3">
        {jobs === null ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : jobs.length === 0 ? (
          <div className="rounded-card border border-border bg-bg-secondary p-4 text-sm text-text-secondary">
            {error ?? "No jobs yet."}
          </div>
        ) : (
          jobs.map((job) => <JobCard key={job.id} job={job} />)
        )}
      </div>
    </section>
  );
}

