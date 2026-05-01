import { getRequiredPublicEnv } from "../components/env";

export async function fetchClientApi(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const apiUrl = getRequiredPublicEnv("NEXT_PUBLIC_API_URL");

  return fetch(`${apiUrl}${path}`, {
    ...init,
    credentials: "include",
  });
}
