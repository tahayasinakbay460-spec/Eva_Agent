"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { DEFAULT_LOCALE, messages } from "@/i18n";
import { ApiError, type SignUpForm } from "@/lib/api/client";
import { PasskeyError } from "@/lib/webauthn";

const t = messages();

type Mode = "sign_up" | "sign_in";

function errorText(err: unknown): string {
  if (err instanceof PasskeyError) return t.onboarding.errors[err.reason];
  if (err instanceof ApiError) return t.onboarding.errors.failed;
  return t.onboarding.errors.network;
}

/**
 * First-use screen. Sign-up asks for a name plus the 18+ (§12) and AI-disclosure (§7)
 * declarations, then creates a passkey. Returning users sign in with their passkey.
 */
export function Onboarding({
  signUp,
  signIn,
}: {
  signUp: (form: SignUpForm) => Promise<void>;
  signIn: () => Promise<void>;
}) {
  const [mode, setMode] = useState<Mode>("sign_up");
  const [name, setName] = useState("");
  const [adult, setAdult] = useState(false);
  const [understood, setUnderstood] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function attempt(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorText(err));
      setBusy(false);
    }
  }

  function submitSignUp(e: FormEvent) {
    e.preventDefault();
    if (!canSignUp) return;
    void attempt(() =>
      signUp({
        display_name: name.trim(),
        locale: DEFAULT_LOCALE,
        age_confirmed: true,
        ai_disclosure_accepted: true,
      }),
    );
  }

  function switchMode(next: Mode) {
    setMode(next);
    setError(null);
  }

  const canSignUp = name.trim().length > 0 && adult && understood && !busy;

  return (
    <main className="flex min-h-dvh flex-col justify-end px-5 pb-10 pt-16">
      <div className="mb-auto">
        <div className="wordmark text-5xl">EVA</div>
        <p className="mt-1 font-script text-2xl text-accent/90">{t.app.tagline}</p>
      </div>

      {mode === "sign_up" ? (
        <form onSubmit={submitSignUp} className="card space-y-4 p-5">
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
              autoComplete="given-name"
              className="mt-1 w-full rounded-xl border border-border bg-bg-0/60 px-4 py-3 text-base outline-none focus:border-accent"
            />
          </label>
          <p className="rounded-xl border border-amber/30 bg-amber/10 px-3 py-2 text-xs leading-relaxed text-amber">
            {t.onboarding.disclosure}
          </p>
          <Checkbox checked={understood} onChange={setUnderstood}>
            {t.onboarding.disclosureConfirm}
          </Checkbox>
          <Checkbox checked={adult} onChange={setAdult}>
            {t.onboarding.ageConfirm}
          </Checkbox>
          <p className="text-xs leading-relaxed text-muted">{t.onboarding.passkeyHint}</p>
          {error && (
            <p role="alert" className="text-xs text-red-300">
              {error}
            </p>
          )}
          <PrimaryButton type="submit" disabled={!canSignUp}>
            {t.onboarding.createAccount}
          </PrimaryButton>
          <SecondaryButton onClick={() => switchMode("sign_in")} disabled={busy}>
            {t.onboarding.haveAccount}
          </SecondaryButton>
        </form>
      ) : (
        <div className="card space-y-4 p-5">
          <div>
            <h1 className="text-2xl font-semibold">{t.onboarding.signInTitle}</h1>
            <p className="mt-1 text-sm text-muted">{t.onboarding.signInBody}</p>
          </div>
          {error && (
            <p role="alert" className="text-xs text-red-300">
              {error}
            </p>
          )}
          <PrimaryButton onClick={() => void attempt(signIn)} disabled={busy}>
            {t.onboarding.signIn}
          </PrimaryButton>
          <SecondaryButton onClick={() => switchMode("sign_up")} disabled={busy}>
            {t.onboarding.backToSignUp}
          </SecondaryButton>
        </div>
      )}
    </main>
  );
}

function Checkbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3 text-sm leading-snug">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-accent)]"
      />
      <span>{children}</span>
    </label>
  );
}

function PrimaryButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  return (
    <button
      type="button"
      {...props}
      className="w-full rounded-xl bg-gradient-to-r from-accent to-accent-2 py-3 font-semibold text-white disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function SecondaryButton({
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode }) {
  return (
    <button
      type="button"
      {...props}
      className="w-full py-1 text-sm text-muted underline-offset-4 hover:underline disabled:opacity-50"
    >
      {children}
    </button>
  );
}
