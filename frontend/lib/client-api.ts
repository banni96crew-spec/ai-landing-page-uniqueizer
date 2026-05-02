function stripTrailingSlash(url: string): string {
  return url.replace(/\/$/, "");
}

/**
 * Browser: same-origin `/api/...` when NEXT_PUBLIC_API_URL is unset (proxied by
 * next.config rewrites) so session cookies stay on the UI host.
 * With NEXT_PUBLIC_API_URL set, calls go there (cross-origin; cookies only if same-site).
 */
export async function fetchClientApi(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  if (!path.startsWith("/")) {
    throw new Error("fetchClientApi expects path starting with /");
  }

  const explicit = process.env.NEXT_PUBLIC_API_URL?.trim();

  let url: string;
  if (typeof window !== "undefined") {
    url = explicit ? `${stripTrailingSlash(explicit)}${path}` : path;
  } else {
    const origin =
      process.env.API_PROXY_ORIGIN?.trim() ||
      explicit ||
      "http://127.0.0.1:8000";
    url = `${stripTrailingSlash(origin)}${path}`;
  }

  return fetch(url, {
    ...init,
    credentials: "include",
  });
}
