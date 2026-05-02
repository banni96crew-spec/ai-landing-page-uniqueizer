import type { ReactNode } from "react";

import { DashboardAuthGate } from "../../components/DashboardAuthGate";

export default function DashboardLayout({
  children,
}: {
  children: ReactNode;
}) {
  return <DashboardAuthGate>{children}</DashboardAuthGate>;
}
