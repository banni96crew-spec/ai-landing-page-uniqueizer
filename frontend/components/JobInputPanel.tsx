"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { getRequiredPublicEnv } from "./env";

type CreateJobOk = {
  id: number;
  status: "pending" | "running" | "done" | "failed";
  created_at: string;
  target_url: string;
};

type CreateJobErrorBody = {
  detail?: string;
  error?: string;
};

export function JobInputPanel() {
  const router = useRouter();
  const [url, setUrl] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    let apiUrl = "";
    try {
      apiUrl = getRequiredPublicEnv("NEXT_PUBLIC_API_URL");
    } catch {
      setError("API URL is not configured");
      return;
    }

    if (!apiUrl) {
      setError("API URL is not configured");
      return;
    }

    setIsLoading(true);
    try {
      const res = await fetch(`${apiUrl}/api/jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_url: url }),
      });

      if (!res.ok) {
        let message = `Error ${res.status}`;
        try {
          const body = (await res.json()) as CreateJobErrorBody;
          const raw = body.detail ?? body.error ?? message;
          if (raw === "queue_full") {
            message = "Queue is full, please try again later";
          } else {
            message = raw;
          }
        } catch {
          // ignore JSON parse errors
        }
        setError(message);
        return;
      }

      const data = (await res.json()) as CreateJobOk;
      setError(null);
      router.push(`/jobs/${data.id}`);
    } catch {
      setError("Network error, please try again");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <section className="mx-auto mt-16 flex w-full max-w-2xl flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
        AI Landing Page Uniqueizer
      </h1>

      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com"
          className="w-full rounded-card border border-border bg-bg-secondary px-4 py-3 font-mono text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
          required
        />

        <button
          type="submit"
          disabled={isLoading}
          className="w-full rounded-card bg-accent py-3 font-semibold text-white transition-colors duration-200 hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isLoading ? "Processing..." : "Uniqueize Landing"}
        </button>

        {error !== null ? (
          <div className="mt-2 text-center text-sm text-error">{error}</div>
        ) : null}
      </form>
    </section>
  );
}

