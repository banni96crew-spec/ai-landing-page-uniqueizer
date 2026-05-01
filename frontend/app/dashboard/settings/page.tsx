import { SettingsForm } from "../../../components/SettingsForm";

export default function DashboardSettingsPage() {
  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto w-full max-w-3xl py-12">
        <h1 className="text-2xl font-semibold tracking-tight text-text-primary">
          Settings
        </h1>
        <div className="mt-8">
          <SettingsForm />
        </div>
      </div>
    </main>
  );
}
