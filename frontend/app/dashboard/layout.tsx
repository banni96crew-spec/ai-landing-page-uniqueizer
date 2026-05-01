import type { ReactNode } from "react";

import { requireAuthenticatedSession } from "../../lib/server-api";

type DashboardLayoutProps = {
  children: ReactNode;
};

export default async function DashboardLayout({
  children,
}: DashboardLayoutProps) {
  await requireAuthenticatedSession();

  return children;
}
