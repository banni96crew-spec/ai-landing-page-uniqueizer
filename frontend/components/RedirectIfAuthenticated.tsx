"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { fetchClientApi } from "../lib/client-api";

/** Client-side session check: API cookie is not visible to Next SSR. */
export function RedirectIfAuthenticated() {
  const router = useRouter();

  useEffect(() => {
    let alive = true;

    (async () => {
      try {
        const res = await fetchClientApi("/api/auth/session", {
          method: "GET",
          cache: "no-store",
        });
        if (!alive || !res.ok) {
          return;
        }
        router.replace("/dashboard");
      } catch {
        // Stay on login/register
      }
    })();

    return () => {
      alive = false;
    };
  }, [router]);

  return null;
}
