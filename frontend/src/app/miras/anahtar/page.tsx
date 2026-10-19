"use client";

/**
 * Miras — alıcının ekranı (ADR 0010, adım 7–8): e-postadaki anahtarı yaz → anahtarın gittiği
 * adrese gelen kodu gir → Miras açılır. Altta paylaşılanlar: konuş, veda et (arşiv), kendi
 * tarafından sil.
 */

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { ArrowLeft, MicIcon, SendIcon } from "@/components/icons";
import { ErrorText, PrimaryButton, TextField } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  ApiError,
  archiveSharedLegacy,
  deleteSharedLegacy,
  listSharedLegacies,
  redeemLegacy,
  verifyLegacyRedeem,
  type SharedLegacy,
} from "@/lib/api/client";

const t = messages().legacy;

export default function RedeemPage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return <Redeem />;
}

function redeemError(err: unknown): string {
  return err instanceof ApiError && err.status === 429 ? t.locked : t.invalid;
}

function Redeem() {
  const [key, setKey] = useState("");
  const [flow, setFlow] = useState<{ id: string; email: string } | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [shared, setShared] = useState<SharedLegacy[]>([]);
  // Silme iki dokunuşla: ilki onay ister.
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listSharedLegacies()
      .then((list) => {
        if (!cancelled) setShared(list);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function refresh() {
    setShared(await listSharedLegacies());
  }

  async function submitKey(e: FormEvent) {
    e.preventDefault();
    if (!key.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const started = await redeemLegacy(key.trim());
      setFlow({ id: started.flow_id, email: started.email_hint });
    } catch (err) {
      setError(redeemError(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    if (!flow || code.length !== 6 || busy) return;
    setBusy(true);
    setError(null);
    try {
      const opened = await verifyLegacyRedeem(flow.id, code);
      setNotice(t.opened.replace("{name}", opened.owner_name));
      setFlow(null);
      setKey("");
      setCode("");
      await refresh();
    } catch (err) {
      setError(redeemError(err));
    } finally {
      setBusy(false);
    }
  }

  async function archive(id: string) {
    try {
      await archiveSharedLegacy(id);
      await refresh();
    } catch {
      setError(t.errors.generic);
    }
  }

  async function remove(id: string) {
    if (confirming !== id) {
      setConfirming(id);
      return;
    }
    setConfirming(null);
    try {
      await deleteSharedLegacy(id);
      await refresh();
    } catch {
      setError(t.errors.generic);
    }
  }

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg-0/80 px-3 py-3 backdrop-blur-xl">
        <Link
          href="/profil"
          aria-label="Geri"
          className="rounded-full p-1 text-muted hover:text-white"
        >
          <ArrowLeft />
        </Link>
        <span className="flex-1 font-semibold">{t.redeemTitle}</span>
      </header>
      <main className="mx-auto max-w-md space-y-6 px-4 py-5">
        <p className="text-sm text-muted">{t.redeemSubtitle}</p>

        {!flow ? (
          <form onSubmit={submitKey} className="space-y-3">
            <TextField
              label={t.keyLabel}
              placeholder={t.keyPlaceholder}
              value={key}
              autoComplete="off"
              spellCheck={false}
              maxLength={80}
              onChange={(e) => setKey(e.target.value)}
            />
            <PrimaryButton type="submit" disabled={busy || key.trim().length < 10}>
              {t.continue}
            </PrimaryButton>
          </form>
        ) : (
          <form onSubmit={submitCode} className="space-y-3">
            <p className="text-sm">{t.codeSent.replace("{email}", flow.email)}</p>
            <TextField
              label={t.codeLabel}
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              maxLength={6}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
            <PrimaryButton type="submit" disabled={busy || code.length !== 6}>
              {t.open}
            </PrimaryButton>
          </form>
        )}
        {error && <ErrorText>{error}</ErrorText>}
        {notice && <p className="text-sm text-mint">{notice}</p>}

        {shared.length > 0 && (
          <section className="space-y-3">
            <h2 className="font-semibold">{t.sharedTitle}</h2>
            <ul className="space-y-3">
              {shared.map((s) => (
                <li key={s.access_id} className="space-y-2 rounded-2xl bg-white/5 p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{s.owner_name}</span>
                    {s.status !== "active" && (
                      <span className="text-xs text-muted">
                        {s.status === "archived" ? t.archived : t.revokedByOwner}
                      </span>
                    )}
                  </div>
                  {s.status === "active" && (
                    <div className="flex gap-2">
                      <Link
                        href={`/chat?miras=${s.persona_id}`}
                        className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-white/10 py-2 text-sm font-semibold"
                      >
                        <SendIcon size={14} /> {t.talk}
                      </Link>
                      <Link
                        href={`/gorusme?miras=${s.persona_id}`}
                        className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-gradient-to-r from-accent to-accent-2 py-2 text-sm font-semibold"
                      >
                        <MicIcon size={14} /> {t.call}
                      </Link>
                    </div>
                  )}
                  <div className="flex justify-between text-xs text-muted">
                    {s.status === "active" ? (
                      <button
                        type="button"
                        className="underline"
                        onClick={() => void archive(s.access_id)}
                      >
                        {t.archive}
                      </button>
                    ) : (
                      <span />
                    )}
                    <button
                      type="button"
                      onClick={() => void remove(s.access_id)}
                      className={confirming === s.access_id ? "text-red-300" : "underline"}
                    >
                      {confirming === s.access_id ? t.removeConfirm : t.remove}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}
