"use client";

import { useEffect, useState } from "react";

import { fetchClientApi } from "../lib/client-api";

type SettingResponse = { key: string; value: string };
type SettingUpsertRequest = { key: string; value: string };
const HIDDEN_SETTINGS_KEYS = new Set(["anthropic_api_key", "anthropic_model"]);

export function SettingsForm() {
  const [settings, setSettings] = useState<Record<string, string>>({});
  const [original, setOriginal] = useState<Record<string, string>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isDirty =
    JSON.stringify(settings) !== JSON.stringify(original) && !isSaving;

  useEffect(() => {
    let alive = true;
    async function load() {
      setError(null);
      try {
        const res = await fetchClientApi("/api/settings", { method: "GET" });
        if (!res.ok) {
          setError(`Error ${res.status}`);
          return;
        }
        const data = (await res.json()) as SettingResponse[];
        if (!alive) return;

        const map: Record<string, string> = {};
        for (const item of data) {
          if (HIDDEN_SETTINGS_KEYS.has(item.key)) {
            continue;
          }
          map[item.key] = item.value;
        }
        setSettings(map);
        setOriginal(map);
      } catch {
        if (!alive) return;
        setError("Network error");
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, []);

  async function onSave() {
    setIsSaving(true);
    setError(null);
    setToast(null);
    try {
      const payload: SettingUpsertRequest[] = Object.entries(settings).map(
        ([key, value]) => ({ key, value }),
      );

      const res = await fetchClientApi("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        setError(`Error ${res.status}`);
        return;
      }

      setOriginal(settings);
      setToast("Settings saved");
      window.setTimeout(() => setToast(null), 2000);
    } catch {
      setError("Network error");
    } finally {
      setIsSaving(false);
    }
  }

  const keys = Object.keys(settings)
    .filter((key) => !HIDDEN_SETTINGS_KEYS.has(key))
    .sort((a, b) => a.localeCompare(b));

  return (
    <section className="mx-auto flex w-full max-w-xl flex-col gap-4">
      {error ? <div className="text-sm text-error">{error}</div> : null}
      {toast ? <div className="text-sm text-success">{toast}</div> : null}

      <div className="flex flex-col gap-4">
        {keys.map((key) => {
          const value = settings[key] ?? "";
          const isApiKey = key.endsWith("_api_key");
          return (
            <label key={key} className="flex flex-col gap-2">
              <span className="text-sm text-text-secondary">{key}</span>
              <input
                value={value}
                onChange={(e) =>
                  setSettings((prev) => ({ ...prev, [key]: e.target.value }))
                }
                type={isApiKey ? "password" : "text"}
                className="w-full rounded-card border border-border bg-bg-secondary px-4 py-3 font-mono text-sm text-text-primary placeholder:text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent"
              />
            </label>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onSave}
        disabled={!isDirty || isSaving}
        className="mt-2 w-full rounded-card bg-accent py-3 font-semibold text-white transition-colors duration-200 hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isSaving ? "Saving..." : "Save settings"}
      </button>
    </section>
  );
}

