"use client";

import Link from "next/link";
import { useState } from "react";

import { fetchClientApi } from "../../lib/client-api";
import { formatApiErrorPayload } from "../../lib/format-api-error";
import type {
  AccountResponse,
  LicenseVerifyRequest,
  LicenseVerifyResponse,
} from "../types";
import {
  formatAccountPlan,
  formatQuotaSummary,
  formatSitesRemaining,
} from "./account-format";

type ActivationPanelProps = {
  initialAccount: AccountResponse;
};

export function ActivationPanel({ initialAccount }: ActivationPanelProps) {
  const [account, setAccount] = useState<AccountResponse>(initialAccount);
  const [activationKey, setActivationKey] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setIsSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const payload: LicenseVerifyRequest = { activation_key: activationKey };
      const response = await fetchClientApi("/api/license/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let message = `Error ${response.status}`;
        try {
          message = formatApiErrorPayload(await response.json(), message);
        } catch {
          // Ignore invalid error bodies and fall back to HTTP status text.
        }
        setError(message);
        return;
      }

      const nextAccount = (await response.json()) as LicenseVerifyResponse;
      setAccount(nextAccount);
      setActivationKey("");
      setSuccess(`Plan updated to ${formatAccountPlan(nextAccount.plan)}.`);
    } catch {
      setError("Network error, please try again");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <form
        onSubmit={onSubmit}
        className="rounded-3xl border border-border bg-bg-secondary/50 p-6 shadow-[0_18px_48px_rgba(0,0,0,0.24)]"
      >
        <h2 className="text-lg font-semibold text-text-primary">
          Activate license
        </h2>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          Submit your activation key to validate it with the licensing backend
          and update the local account plan.
        </p>

        <label className="mt-6 flex flex-col gap-2">
          <span className="text-sm font-medium text-text-secondary">
            Activation key
          </span>
          <input
            value={activationKey}
            onChange={(event) => setActivationKey(event.target.value)}
            placeholder="XXXX-XXXX-XXXX"
            autoComplete="off"
            required
            className="w-full rounded-card border border-border bg-bg-primary px-4 py-3 font-mono text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </label>

        {error ? <p className="mt-4 text-sm text-error">{error}</p> : null}
        {success ? <p className="mt-4 text-sm text-success">{success}</p> : null}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row">
          <button
            type="submit"
            disabled={isSubmitting || activationKey.trim().length === 0}
            className="rounded-card bg-accent px-5 py-3 font-semibold text-white transition-colors duration-200 hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isSubmitting ? "Verifying..." : "Verify activation key"}
          </button>
          <Link
            href="/dashboard/account"
            className="rounded-card border border-border px-5 py-3 text-center text-sm font-medium text-text-secondary transition-colors hover:border-accent hover:text-text-primary"
          >
            Back to account
          </Link>
        </div>
      </form>

      <aside className="rounded-3xl border border-border bg-bg-secondary/35 p-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
          Current access
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-text-primary">
          {formatAccountPlan(account.plan)}
        </h2>
        <p className="mt-2 text-sm leading-6 text-text-secondary">
          {formatQuotaSummary(account)}
        </p>

        <dl className="mt-6 space-y-4">
          <div>
            <dt className="text-xs uppercase tracking-[0.16em] text-text-secondary">
              Sites remaining
            </dt>
            <dd className="mt-1 text-lg font-semibold text-text-primary">
              {formatSitesRemaining(account)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-[0.16em] text-text-secondary">
              Sites used
            </dt>
            <dd className="mt-1 text-lg font-semibold text-text-primary">
              {account.sites_used}
            </dd>
          </div>
        </dl>

        <p className="mt-6 text-sm leading-6 text-text-secondary">
          Only successfully completed jobs count against limited plans.
        </p>
      </aside>
    </div>
  );
}
