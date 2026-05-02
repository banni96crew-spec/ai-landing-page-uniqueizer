"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { fetchClientApi } from "../lib/client-api";

export function HomeRedirect() {
  const router = useRouter();

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        const res = await fetchClientApi("/api/auth/session", {
          method: "GET",
          cache: "no-store",
        });
        if (!alive) {
          return;
        }
        router.replace(res.ok ? "/dashboard" : "/login");
      } catch {
        if (alive) {
          router.replace("/login");
        }
      }
    })();

    return () => {
      alive = false;
    };
  }, [router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary text-sm text-text-secondary">
      Loading…
    </div>
  );
}
