"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { setStoredPasswordForAccountDisplay } from "../../lib/account-password-display";
import { fetchClientApi } from "../../lib/client-api";
import { formatApiErrorPayload } from "../../lib/format-api-error";
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
} from "../types";

type AuthMode = "login" | "register";

type AuthFormProps = {
  mode: AuthMode;
};

export function AuthForm({ mode }: AuthFormProps) {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [telegramUsername, setTelegramUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isRegister = mode === "register";

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      const endpoint = isRegister ? "/api/auth/register" : "/api/auth/login";
      const payload: LoginRequest | RegisterRequest = isRegister
        ? {
            login,
            password,
            telegram_username: telegramUsername,
          }
        : {
            login,
            password,
          };

      const response = await fetchClientApi(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        let message = `Error ${response.status}`;
        try {
          message = formatApiErrorPayload(await response.json(), message);
        } catch {
          // Ignore malformed error payloads and fall back to the status code.
        }
        setError(message);
        return;
      }

      await response.json() as LoginResponse | RegisterResponse;
      setStoredPasswordForAccountDisplay(password);
      // #region agent log
      fetch(
        "http://127.0.0.1:7257/ingest/47461072-dce2-4906-9471-72a4323407ed",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Debug-Session-Id": "bec52b",
          },
          body: JSON.stringify({
            sessionId: "bec52b",
            runId: "post-fix",
            location: "AuthForm.tsx:onSubmit",
            message: "Auth success — client password persistence",
            data: {
              hypothesisId: "H2",
              mode: isRegister ? "register" : "login",
              passwordStoredForDisplayElsewhere: true,
            },
            timestamp: Date.now(),
          }),
        },
      ).catch(() => {});
      // #endregion
      router.push("/dashboard");
      router.refresh();
    } catch {
      setError("Network error, please try again");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-md rounded-3xl border border-border bg-bg-secondary/50 p-8 shadow-[0_18px_48px_rgba(0,0,0,0.24)]">
      <h1 className="text-3xl font-semibold tracking-tight text-text-primary">
        {isRegister ? "Register" : "Login"}
      </h1>
      <p className="mt-3 text-sm leading-6 text-text-secondary">
        {isRegister
          ? "Create the single local account used to manage jobs, settings, and license activation."
          : "Sign in to continue to the protected dashboard area."}
      </p>

      <form onSubmit={onSubmit} className="mt-8 flex flex-col gap-4">
        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-text-secondary">Login</span>
          <input
            value={login}
            onChange={(event) => setLogin(event.target.value)}
            autoComplete="username"
            required
            className="w-full rounded-card border border-border bg-bg-primary px-4 py-3 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </label>

        <label className="flex flex-col gap-2">
          <span className="text-sm font-medium text-text-secondary">Password</span>
          <input
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            required
            className="w-full rounded-card border border-border bg-bg-primary px-4 py-3 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
          />
        </label>

        {isRegister ? (
          <label className="flex flex-col gap-2">
            <span className="text-sm font-medium text-text-secondary">
              Telegram username
            </span>
            <input
              value={telegramUsername}
              onChange={(event) => setTelegramUsername(event.target.value)}
              placeholder="@username"
              autoComplete="username"
              className="w-full rounded-card border border-border bg-bg-primary px-4 py-3 text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </label>
        ) : null}

        {error ? <p className="text-sm text-error">{error}</p> : null}

        <button
          type="submit"
          disabled={isSubmitting}
          className="mt-2 rounded-card bg-accent px-5 py-3 font-semibold text-white transition-colors duration-200 hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isSubmitting
            ? isRegister
              ? "Creating account..."
              : "Signing in..."
            : isRegister
              ? "Create account"
              : "Login"}
        </button>
      </form>

      <p className="mt-6 text-sm text-text-secondary">
        {isRegister ? "Already have an account?" : "Need to create the local account?"}{" "}
        <Link
          href={isRegister ? "/login" : "/register"}
          className="font-medium text-accent transition-colors hover:text-accent-hover"
        >
          {isRegister ? "Login" : "Register"}
        </Link>
      </p>
    </div>
  );
}
