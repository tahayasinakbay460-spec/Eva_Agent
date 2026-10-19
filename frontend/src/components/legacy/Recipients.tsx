"use client";

/**
 * Miras alıcıları (ADR 0010, adım 6 ve 9): anahtar gönderme (Miras rızasıyla), anahtarı bir kez
 * gösterme ve erişimi kapatma. Gönderme ve kapatma adım-yukarı doğrulama ister.
 */

import { useState, type FormEvent } from "react";
import { StepUpCancelled } from "@/components/StepUpSheet";
import { Checkbox, ErrorText, PrimaryButton, SecondaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import {
  createLegacyGrant,
  errorCode,
  revokeLegacyGrant,
  type LegacyConsentText,
  type LegacyGrant,
} from "@/lib/api/client";

const t = messages().legacy;

export function legacyError(err: unknown): string {
  const code = errorCode(err) as keyof typeof t.errors | null;
  return (code && t.errors[code]) || t.errors.generic;
}

export function Recipients({
  grants,
  consent,
  canSend,
  ensure,
  onChanged,
}: {
  grants: LegacyGrant[];
  consent: LegacyConsentText | null;
  canSend: boolean;
  ensure: <T>(action: () => Promise<T>) => Promise<T>;
  onChanged: () => void;
}) {
  const [email, setEmail] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Anahtar yalnızca gönderimin cevabında gelir; bu pencere kapanınca bir daha görünmez.
  const [shownKey, setShownKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!consent || !agreed || !email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const created = await ensure(() => createLegacyGrant(email.trim(), consent.version));
      setShownKey(created.key);
      setEmail("");
      setAgreed(false);
      onChanged();
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(legacyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    if (confirming !== id) {
      setConfirming(id);
      return;
    }
    setConfirming(null);
    setError(null);
    try {
      await ensure(() => revokeLegacyGrant(id));
      onChanged();
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(legacyError(err));
    }
  }

  async function copy() {
    if (!shownKey) return;
    try {
      await navigator.clipboard.writeText(shownKey);
      setCopied(true);
    } catch {
      /* pano izni yoksa kullanıcı elle seçip kopyalar */
    }
  }

  return (
    <div className="space-y-4">
      {grants.length === 0 ? (
        <p className="text-sm text-muted">{t.noGrants}</p>
      ) : (
        <ul className="space-y-2">
          {grants.map((g) => (
            <li key={g.id} className="flex items-center gap-3 rounded-xl bg-white/5 p-3 text-sm">
              <span className="min-w-0 flex-1">
                <span className="block truncate">{g.recipient_email}</span>
                <span className="block text-xs text-muted">{t.status[g.status]}</span>
              </span>
              {(g.status === "pending" || g.status === "redeemed") && (
                <button
                  type="button"
                  onClick={() => void revoke(g.id)}
                  className={`shrink-0 text-xs ${confirming === g.id ? "text-red-300" : "text-muted underline"}`}
                >
                  {confirming === g.id ? t.revokeConfirm : t.revoke}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {canSend && consent && (
        <form onSubmit={send} className="space-y-3 rounded-2xl bg-white/5 p-3">
          <TextField
            label={t.recipientEmail}
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <div className="space-y-2">
            <span className="text-sm text-muted">{t.consentTitle}</span>
            <Checkbox checked={agreed} onChange={setAgreed}>
              {consent.text}
            </Checkbox>
          </div>
          {error && <ErrorText>{error}</ErrorText>}
          <PrimaryButton type="submit" disabled={busy || !agreed || !email.trim()}>
            {t.send}
          </PrimaryButton>
        </form>
      )}
      {!canSend && error && <ErrorText>{error}</ErrorText>}

      {shownKey && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center"
        >
          <div className="w-full max-w-md space-y-4 rounded-3xl border border-border bg-bg-0 p-5">
            <h2 className="text-lg font-semibold">{t.keyTitle}</h2>
            <p className="select-all break-all rounded-xl bg-white/5 p-3 font-mono text-sm">
              {shownKey}
            </p>
            <p className="text-xs text-muted">{t.keyOnce}</p>
            <PrimaryButton onClick={() => void copy()}>{copied ? t.copied : t.copy}</PrimaryButton>
            <SecondaryButton
              onClick={() => {
                setShownKey(null);
                setCopied(false);
              }}
            >
              {t.close}
            </SecondaryButton>
          </div>
        </div>
      )}
    </div>
  );
}
