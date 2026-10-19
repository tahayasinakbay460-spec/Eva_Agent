"use client";

/**
 * Kayıt incelemeleri (yalnızca admin; Faz 3). Sahibin kararı: yüz eşleştirme / yaş tahmini
 * sağlayıcısı olmadığı için her ses/yüz kaydını bir insan onaylar. İnceleyici dosyaları açar
 * (her açılış denetim kaydına yazılır), dört maddeyi tek tek işaretler ve karar verir.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { ArrowLeft } from "@/components/icons";
import { DeathReportsReview } from "@/components/legacy/DeathReportsReview";
import { StepUpCancelled, useStepUp } from "@/components/StepUpSheet";
import { Checkbox, ErrorText } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  approveEnrollment,
  pendingReviews,
  rejectEnrollment,
  reviewFileUrl,
  type AdminEnrollment,
  type RejectReason,
} from "@/lib/api/client";

const t = messages();
const CHECKS = ["adult", "same_person", "code_matches", "consent_is_clear"] as const;
const REASONS = Object.keys(t.media.reasons) as RejectReason[];

export default function Page() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return <Review myId={state.user.id} />;
}

function Review({ myId }: { myId: string }) {
  const [items, setItems] = useState<AdminEnrollment[] | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { ensure, sheet } = useStepUp();

  const reload = useCallback(async () => {
    try {
      setItems(await pendingReviews());
    } catch {
      setError(t.media.errors.generic);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    pendingReviews()
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch(() => {
        if (!cancelled) setError(t.media.errors.generic);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="min-h-dvh pb-10">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg-0/80 px-3 py-3 backdrop-blur-xl">
        <Link
          href="/profil"
          aria-label="Geri"
          className="rounded-full p-1 text-muted hover:text-white"
        >
          <ArrowLeft />
        </Link>
        <span className="font-semibold">{t.review.title}</span>
      </header>
      <main className="space-y-4 px-4 py-4">
        <p className="text-xs text-muted">{t.review.subtitle}</p>
        {notice && (
          <p role="status" className="text-sm text-mint">
            {notice}
          </p>
        )}
        {error && <ErrorText>{error}</ErrorText>}
        <DeathReportsReview ensure={ensure} />
        {items?.length === 0 && <p className="text-sm text-muted">{t.review.empty}</p>}
        {items?.map((item) => (
          <ReviewCard
            key={item.id}
            item={item}
            mine={item.user_id === myId}
            ensure={ensure}
            onDecided={async () => {
              setNotice(t.review.decided);
              await reload();
            }}
          />
        ))}
      </main>
      {sheet}
    </div>
  );
}

function ReviewCard({
  item,
  mine,
  ensure,
  onDecided,
}: {
  item: AdminEnrollment;
  mine: boolean;
  ensure: <T>(action: () => Promise<T>) => Promise<T>;
  onDecided: () => Promise<void>;
}) {
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [reason, setReason] = useState<RejectReason>("other");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => () => Object.values(urls).forEach((u) => URL.revokeObjectURL(u)), [urls]);

  async function guarded(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await ensure(action);
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(t.media.errors.generic);
      throw err;
    } finally {
      setBusy(false);
    }
  }

  async function openFile(fileId: string) {
    let url = "";
    await guarded(async () => {
      url = await reviewFileUrl(item.id, fileId);
    }).catch(() => undefined);
    if (url) setUrls((u) => ({ ...u, [fileId]: url }));
  }

  const allChecked = CHECKS.every((c) => checked[c]);
  return (
    <section className="card space-y-3 p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">
          {item.user_display_name} · {t.media.kinds[item.kind]}
        </h2>
        <span className="text-[11px] text-muted">
          {item.submitted_at ? new Date(item.submitted_at).toLocaleString("tr-TR") : ""}
        </span>
      </div>
      {mine && <p className="text-xs text-amber">{t.review.selfNote}</p>}
      <div>
        <p className="text-xs text-muted">{t.review.expected}</p>
        <blockquote className="mt-1 rounded-xl bg-white/5 p-3 text-sm">
          {item.consent_sentence}
        </blockquote>
      </div>
      <ul className="space-y-2">
        {item.files.map((f) => (
          <li key={f.id} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span>
                {f.role === "consent_recording" ? t.media.stepConsent : t.media.sample} ·{" "}
                {f.duration_s ?? "?"} sn
              </span>
              {!urls[f.id] && (
                <button
                  type="button"
                  disabled={busy}
                  className="underline"
                  onClick={() => void openFile(f.id)}
                >
                  {t.review.open}
                </button>
              )}
            </div>
            {urls[f.id] &&
              (f.media_type.startsWith("image/") ? (
                // eslint-disable-next-line @next/next/no-img-element -- şifreli dosyanın geçici blob adresi
                <img src={urls[f.id]} alt="" className="max-h-96 rounded-xl" />
              ) : f.media_type.startsWith("video/") ? (
                <video
                  src={urls[f.id]}
                  controls
                  controlsList="nodownload"
                  className="w-full rounded-xl bg-black"
                />
              ) : (
                <audio src={urls[f.id]} controls controlsList="nodownload" className="w-full" />
              ))}
          </li>
        ))}
      </ul>
      <div className="space-y-2">
        {CHECKS.map((c) => (
          <Checkbox
            key={c}
            checked={!!checked[c]}
            onChange={(v) => setChecked((s) => ({ ...s, [c]: v }))}
          >
            {t.review.checks[c]}
          </Checkbox>
        ))}
      </div>
      <button
        type="button"
        disabled={!allChecked || busy}
        onClick={() =>
          void guarded(() => approveEnrollment(item.id))
            .then(onDecided)
            .catch(() => undefined)
        }
        className="w-full rounded-xl bg-mint/80 py-2.5 font-semibold text-bg-0 disabled:opacity-40"
      >
        {t.review.approve}
      </button>
      <div className="flex gap-2">
        <select
          aria-label={t.review.reasonLabel}
          value={reason}
          onChange={(e) => setReason(e.target.value as RejectReason)}
          className="min-w-0 flex-1 rounded-xl border border-border bg-bg-0 px-3 text-sm"
        >
          {REASONS.map((r) => (
            <option key={r} value={r}>
              {t.media.reasons[r]}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={busy}
          onClick={() =>
            void guarded(() => rejectEnrollment(item.id, reason))
              .then(onDecided)
              .catch(() => undefined)
          }
          className="shrink-0 rounded-xl bg-red-500 px-4 py-2.5 text-sm font-semibold disabled:opacity-40"
        >
          {t.review.reject}
        </button>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </section>
  );
}
