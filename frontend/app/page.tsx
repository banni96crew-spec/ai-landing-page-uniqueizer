import { redirect } from "next/navigation";

import { getAuthenticatedSession } from "../lib/server-api";

export default async function HomePage() {
  const account = await getAuthenticatedSession();
  redirect(account === null ? "/login" : "/dashboard");
}

