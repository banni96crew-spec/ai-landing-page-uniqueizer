import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import type { AccountResponse } from "../components/types";

function getServerApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
}

function buildServerHeaders(initHeaders?: HeadersInit): Headers {
  const requestHeaders = new Headers(initHeaders);
  const cookieHeader = headers().get("cookie");

  if (cookieHeader) {
    requestHeaders.set("cookie", cookieHeader);
  }

  return requestHeaders;
}

export async function fetchServerApi(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  return fetch(`${getServerApiUrl()}${path}`, {
    ...init,
    headers: buildServerHeaders(init.headers),
    cache: init.cache ?? "no-store",
  });
}

export const getAuthenticatedSession = cache(
  async (): Promise<AccountResponse | null> => {
    const response = await fetchServerApi("/api/auth/session", {
      method: "GET",
    });

    if (response.status === 401) {
      return null;
    }

    if (!response.ok) {
      throw new Error(`Failed to validate session: ${response.status}`);
    }

    return (await response.json()) as AccountResponse;
  },
);

export async function requireAuthenticatedSession(): Promise<AccountResponse> {
  const account = await getAuthenticatedSession();
  if (account === null) {
    redirect("/login");
  }

  return account;
}

export async function redirectAuthenticatedUser(): Promise<void> {
  const account = await getAuthenticatedSession();
  if (account !== null) {
    redirect("/dashboard");
  }
}
