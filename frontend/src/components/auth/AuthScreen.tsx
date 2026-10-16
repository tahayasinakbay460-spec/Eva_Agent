"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { DEFAULT_LOCALE, messages } from "@/i18n";
import {
  passkeyLogin,
  passkeySignUp,
  passwordLoginFinish,
  passwordLoginStart,
  passwordResetFinish,
  passwordResetStart,
  passwordSignUpFinish,
  passwordSignUpStart,
  type User,
} from "@/lib/api/client";
import { errorText, type ErrorContext } from "./errors";
import {
  Checkbox,
  ErrorText,
  Heading,
  PrimaryButton,
  SecondaryButton,
  TextField,
} from "@/components/ui";

const t = messages().auth;
const IS_DEV = process.env.NODE_ENV === "development";

type Step =
  | { kind: "sign_up" }
  | { kind: "sign_in"; notice?: string }
  | { kind: "code"; purpose: "signup" | "login"; flowId: string; email: string }
  | { kind: "reset_request" }
  | { kind: "reset_code"; flowId: string; email: string };

/**
 * Sign-up and sign-in (ADR 0002). Passkey is the recommended path; email + password
 * always continues with a code sent to the email. Sign-up requires the 18+ (§12) and
 * AI-disclosure (§7) declarations on both paths.
 */
export function AuthScreen({ onSignedIn }: { onSignedIn: (user: User) => void }) {
  const [step, setStep] = useState<Step>({ kind: "sign_up" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(context: ErrorContext, action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(errorText(err, context));
    } finally {
      setBusy(false);
    }
  }

  function go(next: Step) {
    setStep(next);
    setError(null);
  }

  const shared = { busy, error, run, go, onSignedIn };

  return (
    <main className="flex min-h-dvh flex-col justify-end px-5 pb-10 pt-16">
      <div className="mb-auto">
        <div className="wordmark text-5xl">EVA</div>
        <p className="mt-1 font-script text-2xl text-accent/90">{messages().app.tagline}</p>
      </div>
      {step.kind === "sign_up" && <SignUp {...shared} />}
      {step.kind === "sign_in" && <SignIn {...shared} notice={step.notice} />}
      {step.kind === "code" && <CodeStep {...shared} step={step} />}
      {step.kind === "reset_request" && <ResetRequest {...shared} />}
      {step.kind === "reset_code" && <ResetCode {...shared} step={step} />}
    </main>
  );
}

type Shared = {
  busy: boolean;
  error: string | null;
  run: (context: ErrorContext, action: () => Promise<void>) => Promise<void>;
  go: (step: Step) => void;
  onSignedIn: (user: User) => void;
};

function Card({ onSubmit, children }: { onSubmit?: (e: FormEvent) => void; children: ReactNode }) {
  return (
    <form onSubmit={onSubmit ?? ((e) => e.preventDefault())} className="card space-y-4 p-5">
      {children}
    </form>
  );
}

/* ---------------------------------------------------------------- sign-up */

function SignUp({ busy, error, run, go, onSignedIn }: Shared) {
  const [method, setMethod] = useState<"passkey" | "password">("passkey");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [adult, setAdult] = useState(false);
  const [understood, setUnderstood] = useState(false);

  const declared = name.trim().length > 0 && adult && understood;
  const ready =
    declared && (method === "passkey" || (email.trim().length > 3 && password.length >= 10));

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!ready) return;
    const base = {
      display_name: name.trim(),
      locale: DEFAULT_LOCALE,
      age_confirmed: true as const,
      ai_disclosure_accepted: true as const,
    };
    if (method === "passkey") {
      void run("passkey", async () => onSignedIn(await passkeySignUp(base)));
      return;
    }
    void run("form", async () => {
      const flow = await passwordSignUpStart({ ...base, email: email.trim(), password });
      go({ kind: "code", purpose: "signup", flowId: flow.flow_id, email: email.trim() });
    });
  }

  return (
    <Card onSubmit={submit}>
      <Heading title={t.welcomeTitle} body={t.welcomeBody} />
      <TextField
        label={t.nameLabel}
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={t.namePlaceholder}
        maxLength={80}
        autoComplete="given-name"
        autoFocus
      />
      <MethodToggle method={method} onChange={setMethod} />
      {method === "password" && (
        <>
          <TextField
            label={t.emailLabel}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={t.emailPlaceholder}
            autoComplete="email"
            maxLength={254}
          />
          <TextField
            label={t.passwordLabel}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            minLength={10}
            maxLength={128}
            hint={t.passwordRule}
          />
        </>
      )}
      <p className="rounded-xl border border-amber/30 bg-amber/10 px-3 py-2 text-xs leading-relaxed text-amber">
        {t.disclosure}
      </p>
      <Checkbox checked={understood} onChange={setUnderstood}>
        {t.disclosureConfirm}
      </Checkbox>
      <Checkbox checked={adult} onChange={setAdult}>
        {t.ageConfirm}
      </Checkbox>
      <p className="text-xs leading-relaxed text-muted">
        {method === "passkey" ? t.passkeyHint : t.passwordHint}
      </p>
      {error && <ErrorText>{error}</ErrorText>}
      <PrimaryButton type="submit" disabled={!ready || busy}>
        {method === "passkey" ? t.createWithPasskey : t.createWithPassword}
      </PrimaryButton>
      <SecondaryButton onClick={() => go({ kind: "sign_in" })} disabled={busy}>
        {t.haveAccount}
      </SecondaryButton>
    </Card>
  );
}

function MethodToggle({
  method,
  onChange,
}: {
  method: "passkey" | "password";
  onChange: (m: "passkey" | "password") => void;
}) {
  const option = (value: "passkey" | "password", label: ReactNode) => (
    <button
      type="button"
      role="radio"
      aria-checked={method === value}
      onClick={() => onChange(value)}
      className={`flex-1 rounded-lg px-3 py-2 text-sm transition ${
        method === value ? "bg-white/15 font-semibold text-white" : "text-muted"
      }`}
    >
      {label}
    </button>
  );
  return (
    <div role="radiogroup" className="flex gap-1 rounded-xl border border-border bg-bg-0/60 p-1">
      {option(
        "passkey",
        <>
          {t.methodPasskey}{" "}
          <span className="text-[10px] font-normal text-mint">{t.recommended}</span>
        </>,
      )}
      {option("password", t.methodPassword)}
    </div>
  );
}

/* ---------------------------------------------------------------- sign-in */

function SignIn({ busy, error, run, go, onSignedIn, notice }: Shared & { notice?: string }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim() || !password) return;
    void run("credentials", async () => {
      const flow = await passwordLoginStart(email.trim(), password);
      go({ kind: "code", purpose: "login", flowId: flow.flow_id, email: email.trim() });
    });
  }

  return (
    <Card onSubmit={submit}>
      <Heading title={t.signInTitle} body={t.signInBody} />
      {notice && <p className="text-xs text-mint">{notice}</p>}
      <PrimaryButton
        onClick={() => void run("passkey", async () => onSignedIn(await passkeyLogin()))}
        disabled={busy}
      >
        {t.signInWithPasskey}
      </PrimaryButton>
      <div className="flex items-center gap-3 text-xs text-muted">
        <span className="h-px flex-1 bg-border" />
        {t.or}
        <span className="h-px flex-1 bg-border" />
      </div>
      <TextField
        label={t.emailLabel}
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t.emailPlaceholder}
        autoComplete="username"
        maxLength={254}
      />
      <TextField
        label={t.passwordLabel}
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
        maxLength={128}
      />
      {error && <ErrorText>{error}</ErrorText>}
      <button
        type="submit"
        disabled={busy || !email.trim() || !password}
        className="w-full rounded-xl border border-border bg-white/10 py-3 font-semibold disabled:opacity-50"
      >
        {t.signInWithPassword}
      </button>
      <SecondaryButton onClick={() => go({ kind: "reset_request" })} disabled={busy}>
        {t.forgotPassword}
      </SecondaryButton>
      <SecondaryButton onClick={() => go({ kind: "sign_up" })} disabled={busy}>
        {t.noAccount}
      </SecondaryButton>
    </Card>
  );
}

/* ---------------------------------------------------------------- codes */

function CodeInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <TextField
      label={t.codeLabel}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
      inputMode="numeric"
      autoComplete="one-time-code"
      placeholder="123456"
      autoFocus
    />
  );
}

function DevMailboxHint() {
  return IS_DEV ? <p className="text-[11px] text-muted/80">{t.devMailboxHint}</p> : null;
}

function CodeStep({
  busy,
  error,
  run,
  go,
  onSignedIn,
  step,
}: Shared & { step: Extract<Step, { kind: "code" }> }) {
  const [code, setCode] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (code.length !== 6) return;
    const finish = step.purpose === "signup" ? passwordSignUpFinish : passwordLoginFinish;
    void run("code", async () => onSignedIn(await finish(step.flowId, code)));
  }

  return (
    <Card onSubmit={submit}>
      <Heading title={t.codeTitle} body={t.codeBody.replace("{email}", step.email)} />
      <CodeInput value={code} onChange={setCode} />
      <DevMailboxHint />
      {error && <ErrorText>{error}</ErrorText>}
      <PrimaryButton type="submit" disabled={busy || code.length !== 6}>
        {t.verify}
      </PrimaryButton>
      <SecondaryButton
        onClick={() => go({ kind: step.purpose === "signup" ? "sign_up" : "sign_in" })}
        disabled={busy}
      >
        {t.back}
      </SecondaryButton>
    </Card>
  );
}

/* ---------------------------------------------------------------- reset */

function ResetRequest({ busy, error, run, go }: Shared) {
  const [email, setEmail] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    void run("form", async () => {
      const flow = await passwordResetStart(email.trim(), DEFAULT_LOCALE);
      go({ kind: "reset_code", flowId: flow.flow_id, email: email.trim() });
    });
  }

  return (
    <Card onSubmit={submit}>
      <Heading title={t.resetTitle} body={t.resetBody} />
      <TextField
        label={t.emailLabel}
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder={t.emailPlaceholder}
        autoComplete="email"
        maxLength={254}
        autoFocus
      />
      {error && <ErrorText>{error}</ErrorText>}
      <PrimaryButton type="submit" disabled={busy || !email.trim()}>
        {t.sendCode}
      </PrimaryButton>
      <SecondaryButton onClick={() => go({ kind: "sign_in" })} disabled={busy}>
        {t.back}
      </SecondaryButton>
    </Card>
  );
}

function ResetCode({
  busy,
  error,
  run,
  go,
  step,
}: Shared & { step: Extract<Step, { kind: "reset_code" }> }) {
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (code.length !== 6 || password.length < 10) return;
    void run("code", async () => {
      await passwordResetFinish(step.flowId, code, password);
      go({ kind: "sign_in", notice: t.resetDone });
    });
  }

  return (
    <Card onSubmit={submit}>
      <Heading title={t.resetTitle} body={t.resetCodeBody.replace("{email}", step.email)} />
      <CodeInput value={code} onChange={setCode} />
      <DevMailboxHint />
      <TextField
        label={t.newPasswordLabel}
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="new-password"
        minLength={10}
        maxLength={128}
        hint={t.passwordRule}
      />
      {error && <ErrorText>{error}</ErrorText>}
      <PrimaryButton type="submit" disabled={busy || code.length !== 6 || password.length < 10}>
        {t.setNewPassword}
      </PrimaryButton>
      <SecondaryButton onClick={() => go({ kind: "sign_in" })} disabled={busy}>
        {t.back}
      </SecondaryButton>
    </Card>
  );
}
