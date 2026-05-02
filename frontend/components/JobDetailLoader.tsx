"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { JobDetailClient } from "./JobDetailClient";
import type { JobDetailResponse } from "./types";
import { fetchClientApi } from "../lib/client-api";

type LoaderState =
  | { status: "loading" }
  | { status: "ready"; job: JobDetailResponse }
  | { status: "not_found" }
  | { status: "error"; message: string };

export function JobDetailLoader({ jobId }: { jobId: number }) {
  const router = useRouter();
  const [state, setState] = useState<LoaderState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const res = await fetchClientApi(`/api/jobs/${jobId}`, {
          method: "GET",
          cache: "no-store",
        });

        if (cancelled) {
          return;
        }

        if (res.status === 401) {
          router.replace("/login");
          return;
        }

        if (res.status === 404) {
          setState({ status: "not_found" });
          return;
        }

        if (!res.ok) {
          setState({
            status: "error",
            message: `Could not load job (${res.status})`,
          });
          return;
        }

        const job = (await res.json()) as JobDetailResponse;
        if (!cancelled) {
          setState({ status: "ready", job });
        }
      } catch {
        if (!cancelled) {
          setState({
            status: "error",
            message: "Network error while loading job.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [jobId, router]);

  if (state.status === "loading") {
    return (
      <div className="mt-8 rounded-card border border-border bg-bg-secondary p-8 text-center text-sm text-text-secondary">
        Loading job…
      </div>
    );
  }

  if (state.status === "not_found") {
    return (
      <div className="mt-8 flex flex-col gap-4 rounded-card border border-border bg-bg-secondary p-8">
        <p className="text-text-primary">Job not found.</p>
        <Link
          href="/dashboard"
          className="text-sm text-text-secondary transition-colors hover:text-text-primary"
        >
          ← Back to Dashboard
        </Link>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="mt-8 flex flex-col gap-4 rounded-card border border-border bg-bg-secondary p-8">
        <p className="text-text-primary">{state.message}</p>
        <Link
          href="/dashboard"
          className="text-sm text-text-secondary transition-colors hover:text-text-primary"
        >
          ← Back to Dashboard
        </Link>
      </div>
    );
  }

  return <JobDetailClient initialJob={state.job} />;
}
