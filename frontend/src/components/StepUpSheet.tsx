"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ErrorText, PrimaryButton, SecondaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import {
  errorCode,
  stepUpPasswordFinish,
  stepUpPasswordStart,
  stepUpStatus,
  stepUpWithPasskey,
  type StepUpStatus,
} from "@/lib/api/client";

const t = messages().stepUp;

export class StepUpCancelled extends Error {}

/**
 * Adım-yukarı doğrulama (§11.2). Hassas bir işlem backend'den "step_up_required" alırsa
 * kullanıcıdan kimliğini yeniden doğrulaması istenir, sonra işlem kendiliğinden tekrar denenir.
 *
 *   const { ensure, sheet } = useStepUp();
 *   await ensure(() => startEnrollment(...));
 *   return <>{...}{sheet}</>;
 */
export function useStepUp(): {
  ensure: <T>(action: () => Promise<T>) => Promise<T>;
  sheet: ReactNode;
} {
  const [open, setOpen] = useState(false);
  const pending = useRef<{ resolve: () => void; reject: (err: Error) => void } | null>(null);

  const ensure = useCallback(async <T,>(action: () => Promise<T>): Promise<T> => {
    try {
      return await action();
    } catch (err) {
      if (errorCode(err) !== "step_up_required") throw err;
    }
    await new Promise<void>((resolve, reject) => {
      pending.current = { resolve, reject };
      setOpen(true);
    });
    return action();
  }, []);

  const sheet = open ? (
    <StepUpSheet
      onDone={() => {
        setOpen(false);
        pending.current?.resolve();
      }}
      onCancel={() => {
        setOpen(false);
        pending.current?.reject(new StepUpCancelled());
      }}
    />
  ) : null;
  return { ensure, sheet };
}

function StepUpSheet({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [status, setStatus] = useState<StepUpStatus | null>(null);
  const [password, setPassword] = useState("");
  const [flowId, setFlowId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    stepUpStatus()
      .then((s) => {
        if (!cancelled) setStatus(s);
      })
      .catch(() => {
        if (!cancelled) setError(t.failed);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      await action();
      if (after) after();
      else onDone();
    } catch {
      setError(t.failed);
    } finally {
      setBusy(false);
    }
  }

  const methods = status?.methods ?? [];
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.title}
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 backdrop-blur-sm"
    >
      <div className="card m-3 w-full max-w-[430px] space-y-4 p-5">
        <div>
          <h2 className="text-lg font-semibold">{t.title}</h2>
          <p className="mt-1 text-sm text-muted">{t.body}</p>
        </div>
        {status && methods.length === 0 && <p className="text-sm text-amber">{t.noMethod}</p>}
        {methods.includes("passkey") && (
          <PrimaryButton disabled={busy} onClick={() => void run(() => stepUpWithPasskey())}>
            {t.passkey}
          </PrimaryButton>
        )}
        {methods.includes("password") &&
          (flowId === null ? (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run(
                  async () => setFlowId((await stepUpPasswordStart(password)).flow_id),
                  () => undefined,
                );
              }}
            >
              <TextField
                label={t.passwordLabel}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <PrimaryButton type="submit" disabled={busy || !password}>
                {t.sendCode}
              </PrimaryButton>
            </form>
          ) : (
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                void run(() => stepUpPasswordFinish(flowId, code));
              }}
            >
              <TextField
                label={t.codeLabel}
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
              />
              <PrimaryButton type="submit" disabled={busy || code.length !== 6}>
                {t.verify}
              </PrimaryButton>
            </form>
          ))}
        {error && <ErrorText>{error}</ErrorText>}
        <SecondaryButton onClick={onCancel} disabled={busy}>
          {t.cancel}
        </SecondaryButton>
      </div>
    </div>
  );
}
