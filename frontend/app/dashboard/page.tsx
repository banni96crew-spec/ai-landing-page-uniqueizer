import { JobInputPanel } from "../../components/JobInputPanel";
import { JobList } from "../../components/JobList";

export default function DashboardPage() {
  return (
    <main className="min-h-screen bg-bg-primary px-6">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-10">
        <JobInputPanel />
        <JobList />
      </div>
    </main>
  );
}

