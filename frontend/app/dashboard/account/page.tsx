"use client";

import Link from "next/link";

import {
  formatAccountPlan,
  formatQuotaSummary,
  formatSitesRemaining,
} from "../../../components/account/account-format";
import { useDashboardSession } from "../../../components/DashboardAuthGate";

export default function AccountPage() {
  const account = useDashboardSession();

  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto w-full max-w-5xl py-12">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-text-primary">
              Account
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-text-secondary">
              Account credentials, plan status, and remaining quota are loaded
              from the current backend session.
            </p>
          </div>

          <Link
            href="/dashboard/activation"
            className="inline-flex items-center justify-center rounded-card border border-accent/50 px-4 py-3 text-sm font-medium text-text-primary transition-colors hover:bg-accent hover:text-white"
          >
            Activate license
          </Link>
        </div>

        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <section className="rounded-3xl border border-border bg-bg-secondary/50 p-6 shadow-[0_18px_48px_rgba(0,0,0,0.24)]">
            <h2 className="text-lg font-semibold text-text-primary">
              Local account
            </h2>
            <dl className="mt-6 grid gap-5 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-text-secondary">
                  Login
                </dt>
                <dd className="mt-2 text-base font-medium text-text-primary">
                  {account.login}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-text-secondary">
                  Password
                </dt>
                <dd className="mt-2 text-base font-medium text-text-primary">
                  {"••••••••"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-text-secondary">
                  Telegram
                </dt>
                <dd className="mt-2 text-base font-medium text-text-primary">
                  {account.telegram_username || "Not set"}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-text-secondary">
                  Current plan
                </dt>
                <dd className="mt-2 text-base font-medium text-text-primary">
                  {formatAccountPlan(account.plan)}
                </dd>
              </div>
            </dl>
          </section>

          <aside className="rounded-3xl border border-border bg-bg-secondary/35 p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
              Usage
            </p>
            <h2 className="mt-3 text-2xl font-semibold text-text-primary">
              {formatSitesRemaining(account)}
            </h2>
            <p className="mt-2 text-sm leading-6 text-text-secondary">
              {account.sites_remaining === null
                ? "Sites remaining on your current plan."
                : "Sites remaining before the current plan limit is reached."}
            </p>

            <dl className="mt-6 space-y-4">
              <div>
                <dt className="text-xs uppercase tracking-[0.16em] text-text-secondary">
                  Quota summary
                </dt>
                <dd className="mt-1 text-base font-medium text-text-primary">
                  {formatQuotaSummary(account)}
                </dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-[0.16em] text-text-secondary">
                  Sites used
                </dt>
                <dd className="mt-1 text-base font-medium text-text-primary">
                  {account.sites_used}
                </dd>
              </div>
            </dl>

            <p className="mt-6 text-sm leading-6 text-text-secondary">
              Only `done` jobs consume balance, so failed runs do not reduce your
              remaining quota.
            </p>
          </aside>
        </div>
      </div>
    </main>
  );
}
