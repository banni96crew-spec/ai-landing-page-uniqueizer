import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-bg-primary">
      <h1 className="text-2xl font-semibold text-text-primary">Page Not Found</h1>
      <p className="mt-2 text-sm text-text-secondary">
        The job or page you're looking for doesn't exist.
      </p>
      <Link
        href="/dashboard"
        className="mt-6 text-sm text-accent underline hover:text-accent-hover"
      >
        ← Back to Dashboard
      </Link>
    </main>
  );
}

