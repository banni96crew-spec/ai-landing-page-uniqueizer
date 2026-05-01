import { AuthForm } from "../../components/auth/AuthForm";
import { redirectAuthenticatedUser } from "../../lib/server-api";

export default async function RegisterPage() {
  await redirectAuthenticatedUser();

  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-10 py-16 lg:flex-row lg:items-center lg:justify-between">
        <section className="max-w-xl">
          <p className="text-xs font-semibold uppercase tracking-[0.22em] text-accent">
            Local account setup
          </p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight text-text-primary">
            Create the dashboard account
          </h1>
          <p className="mt-4 text-sm leading-7 text-text-secondary">
            Register the single local operator account that will own the session,
            show plan usage, and submit activation keys for licensing upgrades.
          </p>
        </section>

        <AuthForm mode="register" />
      </div>
    </main>
  );
}
