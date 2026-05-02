"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";

import { fetchClientApi } from "../lib/client-api";
import type { AccountResponse } from "./types";

const DashboardSessionContext = createContext<AccountResponse | null>(null);

export function useDashboardSession(): AccountResponse {
  const account = useContext(DashboardSessionContext);
  if (!account) {
    throw new Error("useDashboardSession must be used within DashboardAuthGate");
  }
  return account;
}

export function DashboardAuthGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [ready, setReady] = useState(false);

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
        if (res.status === 401 || !res.ok) {
          router.replace("/login");
          return;
        }
        const data = (await res.json()) as AccountResponse;
        if (!alive) {
          return;
        }
        setAccount(data);
        setReady(true);
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

  if (!ready || account === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary text-sm text-text-secondary">
        Loading…
      </div>
    );
  }

  return (
    <DashboardSessionContext.Provider value={account}>
      {children}
    </DashboardSessionContext.Provider>
  );
}
