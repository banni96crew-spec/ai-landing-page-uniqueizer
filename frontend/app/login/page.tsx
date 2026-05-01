import { AuthForm } from "../../components/auth/AuthForm";
import { redirectAuthenticatedUser } from "../../lib/server-api";

export default async function LoginPage() {
  await redirectAuthenticatedUser();

  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-10 py-16 lg:flex-row lg:items-center lg:justify-between">
        <section className="max-w-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            Protected access
          </p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight text-text-primary">
            Sign in to AI Landing Page Uniqueizer
          </h1>
          <p className="mt-4 text-sm leading-7 text-text-secondary">
            Use the local account session to access the dashboard, inspect usage,
            and activate higher plan limits.
          </p>
        </section>

        <AuthForm mode="login" />
      </div>
    </main>
  );
}
