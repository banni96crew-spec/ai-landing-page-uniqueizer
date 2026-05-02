"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";

import { clearStoredPasswordForAccountDisplay } from "../lib/account-password-display";
import { fetchClientApi } from "../lib/client-api";

type NavItem = {
  href: string;
  label: string;
  isActive: (pathname: string) => boolean;
};

const navItems: NavItem[] = [
  {
    href: "/dashboard",
    label: "Dashboard",
    isActive: (pathname) =>
      pathname === "/dashboard" || pathname.startsWith("/jobs/"),
  },
  {
    href: "/dashboard/account",
    label: "Account",
    isActive: (pathname) =>
      pathname.startsWith("/dashboard/account") ||
      pathname.startsWith("/dashboard/activation"),
  },
  {
    href: "/dashboard/settings",
    label: "Settings",
    isActive: (pathname) => pathname.startsWith("/dashboard/settings"),
  },
];

function getNavItemClass(isActive: boolean): string {
  return [
    "rounded-full px-4 py-2 text-sm font-medium transition-colors",
    isActive
      ? "bg-accent text-text-primary"
      : "text-text-secondary hover:bg-bg-secondary hover:text-text-primary",
  ].join(" ");
}

export function AppHeader() {
  const pathname = usePathname();
  const router = useRouter();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const isDashboardRoute =
    pathname.startsWith("/dashboard") || pathname.startsWith("/jobs/");

  async function onLogout() {
    setIsLoggingOut(true);
    try {
      await fetchClientApi("/api/auth/logout", {
        method: "POST",
      });
    } finally {
      clearStoredPasswordForAccountDisplay();
      router.push("/login");
      router.refresh();
      setIsLoggingOut(false);
    }
  }

  return (
    <header className="sticky top-0 z-20 border-b border-border/80 bg-bg-primary/90 backdrop-blur">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 px-6 py-5">
        <div className="flex items-center gap-4">
          <Link
            href="/"
            className="text-sm font-semibold uppercase tracking-[0.28em] text-text-primary transition-colors hover:text-accent"
          >
            AI LPU
          </Link>

          {isDashboardRoute ? (
            <nav
              aria-label="Primary"
              className="flex items-center gap-1 rounded-full border border-border/80 bg-bg-secondary/40 p-1"
            >
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={getNavItemClass(item.isActive(pathname))}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          ) : null}
        </div>

        <div className="flex items-center gap-3">
          {!isDashboardRoute ? (
            <div className="flex items-center gap-2">
              <Link
                href="/login"
                className="rounded-full border border-border/80 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:border-accent hover:text-text-primary"
              >
                Login
              </Link>
              <Link
                href="/register"
                className="rounded-full bg-accent px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
              >
                Register
              </Link>
            </div>
          ) : (
            <button
              type="button"
              onClick={onLogout}
              disabled={isLoggingOut}
              className="rounded-full border border-border/80 px-4 py-2 text-sm font-medium text-text-secondary transition-colors hover:border-accent hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoggingOut ? "Logging out..." : "Logout"}
            </button>
          )}

          <a
            href="https://t.me/tg_channel"
            target="_blank"
            rel="noreferrer"
            aria-label="Telegram channel"
            className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border/80 bg-bg-secondary/40 text-text-secondary transition-colors hover:border-accent hover:text-accent"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              className="h-4 w-4 fill-current"
            >
              <path d="M19.68 4.33 3.74 10.47c-1.09.44-1.08 1.05-.2 1.32l4.1 1.28 1.58 5.02c.19.53.1.74.65.74.42 0 .61-.19.84-.42l2.01-1.95 4.18 3.09c.77.43 1.32.21 1.51-.71l2.71-12.78c.28-1.13-.43-1.64-1.44-1.18Zm-10.82 8.45 8.38-5.29c.42-.25.8-.12.48.17l-6.9 6.22-.27 2.92-1.69-4.02Z" />
            </svg>
          </a>
        </div>
      </div>
    </header>
  );
}
