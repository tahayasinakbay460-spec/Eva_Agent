"use client";

/**
 * Vefat sonrası Miras'ı silmek (ADR 0011): üç kez "emin misin" → e-postaya kod → onay.
 * Silinse bile karakter sistemde yaşar; geri getirmek için destek ekibiyle iletişim gerekir.
 */

import { useState, type FormEvent } from "react";
import { ErrorText, PrimaryButton, SecondaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import { startSharedDelete, verifySharedDelete } from "@/lib/api/client";

const t = messages().legacy;

export function PosthumousDelete({
  accessId,
  onClose,
  onDeleted,
}: {
  accessId: string;
  onClose: () => void;
  onDeleted: () => void;
}) {
  // 0, 1, 2: onay soruları · 3: kod
  const [step, setStep] = useState(0);
  const [flow, setFlow] = useState<{ id: string; email: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const questions = [t.deleteAsk1, t.deleteAsk2, t.deleteAsk3];

  async function yes() {
    setError(null);
    if (step < 2) {
      setStep(step + 1);
      return;
    }
    setBusy(true);
    try {
      const started = await startSharedDelete(accessId);
      setFlow({ id: started.flow_id, email: started.email_hint });
      setStep(3);
    } catch {
      setError(t.errors.generic);
    } finally {
      setBusy(false);
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    if (!flow || code.length !== 6) return;
    setBusy(true);
    setError(null);
    try {
      await verifySharedDelete(accessId, flow.id, code);
      onDeleted();
    } catch {
      setError(t.invalid);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
    >
      <div className="w-full max-w-md space-y-4 rounded-3xl border border-border bg-bg-0 p-5">
        {step < 3 ? (
          <>
            <p className="text-sm text-muted">{step + 1} / 3</p>
            <p className="font-semibold">{questions[step]}</p>
            <PrimaryButton disabled={busy} onClick={() => void yes()}>
              {t.deleteYes}
            </PrimaryButton>
          </>
        ) : (
          <form onSubmit={confirm} className="space-y-3">
            <p className="text-sm">{t.deleteCodeSent.replace("{email}", flow?.email ?? "")}</p>
            <TextField
              label={t.codeLabel}
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              maxLength={6}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
            <PrimaryButton type="submit" disabled={busy || code.length !== 6}>
              {t.deleteConfirm}
            </PrimaryButton>
          </form>
        )}
        {error && <ErrorText>{error}</ErrorText>}
        <SecondaryButton onClick={onClose}>{t.deleteCancel}</SecondaryButton>
      </div>
    </div>
  );
}
