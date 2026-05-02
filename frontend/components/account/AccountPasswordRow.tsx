"use client";

import { useEffect, useState } from "react";

import { getStoredPasswordForAccountDisplay } from "../../lib/account-password-display";

const MASK = "••••••••";

function EyeShowIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
      />
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
      />
    </svg>
  );
}

function EyeHideIcon({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className={className}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88"
      />
    </svg>
  );
}

export function AccountPasswordRow() {
  const [stored, setStored] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    setStored(getStoredPasswordForAccountDisplay());
  }, []);

  const canToggle = stored !== null && stored.length > 0;
  const shownText =
    !canToggle ? MASK : visible ? stored : MASK;

  return (
    <div>
      <dt className="text-xs uppercase tracking-[0.18em] text-text-secondary">
        Password
      </dt>
      <dd className="mt-2">
        <div className="flex min-h-7 items-center gap-2">
          <span className="text-base font-medium tracking-wide text-text-primary">
            {shownText}
          </span>
          {canToggle ? (
            <button
              type="button"
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border/80 text-text-secondary transition-colors hover:border-accent hover:text-accent"
              aria-pressed={visible}
              aria-label={visible ? "Hide password" : "Show password"}
              onClick={() => setVisible((prev) => !prev)}
            >
              {visible ? (
                <EyeHideIcon className="h-4 w-4" />
              ) : (
                <EyeShowIcon className="h-4 w-4" />
              )}
            </button>
          ) : null}
        </div>
        {!canToggle ? (
          <p className="mt-2 text-xs leading-5 text-text-secondary">
            Sign in on this browser to unlock show/hide. The server stores only a
            password hash.
          </p>
        ) : null}
      </dd>
    </div>
  );
}
