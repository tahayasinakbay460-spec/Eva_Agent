"use client";

import { useState, type FormEvent } from "react";
import { messages } from "@/i18n";

const t = messages();

/** First-use screen: name + the AI disclosure/consent required by CLAUDE.md §7. */
export function Onboarding({ onDone }: { onDone: (name: string) => Promise<void> }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (name.trim().length < 1 || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onDone(name);
    } catch (err) {
      setError(String(err));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh flex-col justify-end px-5 pb-10 pt-16">
      <div className="mb-auto">
        <div className="wordmark text-5xl">EVA</div>
        <p className="mt-1 font-script text-2xl text-accent/90">{t.app.tagline}</p>
      </div>
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div>
          <h1 className="text-2xl font-semibold">{t.onboarding.title}</h1>
          <p className="mt-1 text-sm text-muted">{t.onboarding.body}</p>
        </div>
        <label className="block text-sm">
          <span className="text-muted">{t.onboarding.nameLabel}</span>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t.onboarding.namePlaceholder}
            maxLength={80}
            className="mt-1 w-full rounded-xl border border-border bg-bg-0/60 px-4 py-3 text-base outline-none focus:border-accent"
          />
        </label>
        <p className="rounded-xl border border-amber/30 bg-amber/10 px-3 py-2 text-xs leading-relaxed text-amber">
          {t.onboarding.disclosure}
        </p>
        {error && <p className="text-xs text-red-300">{error}</p>}
        <button
          type="submit"
          disabled={busy || name.trim().length === 0}
          className="w-full rounded-xl bg-gradient-to-r from-accent to-accent-2 py-3 font-semibold text-white disabled:opacity-50"
        >
          {t.onboarding.accept}
        </button>
      </form>
    </main>
  );
}
