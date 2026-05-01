import { ActivationPanel } from "../../../components/account/ActivationPanel";
import { requireAuthenticatedSession } from "../../../lib/server-api";

export default async function ActivationPage() {
  const account = await requireAuthenticatedSession();

  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto w-full max-w-5xl py-12">
        <h1 className="text-3xl font-semibold tracking-tight text-text-primary">
          Activation
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-text-secondary">
          Upgrade the local account by verifying an activation key against the
          backend licensing service.
        </p>

        <div className="mt-8">
          <ActivationPanel initialAccount={account} />
        </div>
      </div>
    </main>
  );
}
