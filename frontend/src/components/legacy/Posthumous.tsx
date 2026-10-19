"use client";

/**
 * Vefat sonrası Miras (ADR 0011): alıcıları önceden belirle; anahtarlar şimdi gitmez. Hareketsizlik
 * ya da onaylanmış vefat bildirimi -> sahibe uyarı süreci -> anahtarlar otomatik gider.
 * Kaydetme ve kapatma adım-yukarı doğrulama ister.
 */

import { useState, type FormEvent } from "react";
import { StepUpCancelled } from "@/components/StepUpSheet";
import { Checkbox, ErrorText, PrimaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import { configurePosthumous, turnOffPosthumous, type PosthumousSetup } from "@/lib/api/client";
import { legacyError } from "./Recipients";

const t = messages().legacy;
const MAX_HEIRS = 5;

export function Posthumous({
  setup,
  canSetUp,
  ensure,
  onChanged,
}: {
  setup: PosthumousSetup;
  canSetUp: boolean;
  ensure: <T>(action: () => Promise<T>) => Promise<T>;
  onChanged: (setup: PosthumousSetup) => void;
}) {
  const [emails, setEmails] = useState<string[]>(
    setup.heirs.length ? setup.heirs.map((h) => h.email) : [""],
  );
  const [agreed, setAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOff, setConfirmOff] = useState(false);

  const activated = setup.state === "activated";
  const filled = emails.map((e) => e.trim()).filter(Boolean);

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!agreed || filled.length === 0 || busy) return;
    setBusy(true);
    setError(null);
    try {
      onChanged(await ensure(() => configurePosthumous(filled, setup.consent_version)));
      setAgreed(false);
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(legacyError(err));
    } finally {
      setBusy(false);
    }
  }

  async function off() {
    if (!confirmOff) {
      setConfirmOff(true);
      return;
    }
    setConfirmOff(false);
    setError(null);
    try {
      const next = await ensure(() => turnOffPosthumous());
      setEmails([""]);
      onChanged(next);
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(legacyError(err));
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted">{t.posthumousState[setup.state]}</span>
        {setup.state === "warning" && (
          <span className="rounded-full bg-amber/15 px-2 py-0.5 text-xs text-amber">!</span>
        )}
      </div>

      {setup.heirs.length > 0 && (
        <ul className="space-y-1 text-sm">
          {setup.heirs.map((h) => (
            <li key={h.email} className="flex justify-between rounded-lg bg-white/5 px-3 py-2">
              <span className="truncate">{h.email}</span>
              <span className={h.sent ? "text-mint" : "text-muted"}>
                {h.sent ? t.heirSent : t.heirWaiting}
              </span>
            </li>
          ))}
        </ul>
      )}

      {!activated && canSetUp && (
        <form onSubmit={save} className="space-y-3">
          <span className="block text-sm text-muted">{t.heirsLabel}</span>
          {emails.map((value, i) => (
            <TextField
              key={i}
              label={`${i + 1}.`}
              type="email"
              autoComplete="off"
              value={value}
              onChange={(e) =>
                setEmails((list) => list.map((x, j) => (j === i ? e.target.value : x)))
              }
            />
          ))}
          {emails.length < MAX_HEIRS && (
            <button
              type="button"
              onClick={() => setEmails((list) => [...list, ""])}
              className="text-sm text-accent"
            >
              {t.addHeir}
            </button>
          )}
          <Checkbox checked={agreed} onChange={setAgreed}>
            {setup.consent_text}
          </Checkbox>
          <PrimaryButton type="submit" disabled={busy || !agreed || filled.length === 0}>
            {t.saveHeirs}
          </PrimaryButton>
        </form>
      )}

      {!activated && setup.state !== "off" && (
        <button
          type="button"
          onClick={() => void off()}
          className={`text-xs ${confirmOff ? "text-red-300" : "text-muted underline"}`}
        >
          {confirmOff ? t.turnOffConfirm : t.turnOff}
        </button>
      )}
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}
