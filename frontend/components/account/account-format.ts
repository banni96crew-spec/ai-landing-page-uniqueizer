import type { AccountPlan, AccountResponse } from "../types";

const PLAN_LABELS: Record<AccountPlan, string> = {
  trial: "Trial",
  standard: "Standard",
  premium: "Premium",
};

export function formatAccountPlan(plan: AccountPlan): string {
  return PLAN_LABELS[plan];
}

export function formatSitesRemaining(account: AccountResponse): string {
  return account.sites_remaining === null
    ? "Unlimited"
    : String(account.sites_remaining);
}

export function formatQuotaSummary(account: AccountResponse): string {
  if (account.sites_remaining === null) {
    return `${account.sites_used} sites uniqueized with unlimited capacity`;
  }

  const total = account.sites_used + account.sites_remaining;
  return `${account.sites_used} of ${total} sites used`;
}
