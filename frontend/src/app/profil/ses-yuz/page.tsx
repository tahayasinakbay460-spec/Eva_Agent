"use client";

/**
 * "Ses ve yüz" ekranı (Faz 3, CLAUDE.md §11.3). Her tür (ses / yüz) için bir kart:
 *  - rıza metni + onay → kayıt başlar (kimlik yeniden doğrulanır)
 *  - örnekler kaydedilir, rastgele kodlu rıza cümlesi kamerada okunur → incelemeye gönderilir
 *  - inceleme / hazırlanıyor / aktif (sabit cümlelerle dinle) / reddedildi / geri alındı
 *  - "Rızamı geri al": kullanım hemen durur, klon ve kayıtlar silinir.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { ArrowLeft, MicIcon, VideoIcon } from "@/components/icons";
import { StepUpCancelled, useStepUp } from "@/components/StepUpSheet";
import { Checkbox, ErrorText, PrimaryButton, SecondaryButton } from "@/components/ui";
import { useRecorder, type RecordingKind } from "@/hooks/useRecorder";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  consentText,
  deleteEnrollmentFile,
  errorCode,
  listEnrollments,
  previewSentences,
  revokeEnrollment,
  startEnrollment,
  submitEnrollment,
  uploadEnrollmentFile,
  voicePreview,
  type ConsentText,
  type Enrollment,
  type EnrollmentKind,
  type FileRole,
} from "@/lib/api/client";

const t = messages().media;
const KINDS: EnrollmentKind[] = ["voice", "face"];
const OPEN = new Set(["collecting", "pending_review", "processing", "active"]);

export default function Page() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return <MediaScreen />;
}

function MediaScreen() {
  const [enrollments, setEnrollments] = useState<Enrollment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { ensure, sheet } = useStepUp();

  const reload = useCallback(async () => {
    try {
      setEnrollments(await listEnrollments());
    } catch {
      setError(t.errors.generic);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listEnrollments()
      .then((items) => {
        if (!cancelled) setEnrollments(items);
      })
      .catch(() => {
        if (!cancelled) setError(t.errors.generic);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // İnceleme / hazırlanma sürerken durumu ara ara yenile.
  const waiting = enrollments?.some(
    (e) => e.status === "processing" || e.status === "pending_review",
  );
  useEffect(() => {
    if (!waiting) return;
    const id = setInterval(() => void reload(), 5000);
    return () => clearInterval(id);
  }, [waiting, reload]);

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
        <span className="font-semibold">{t.title}</span>
      </header>
      <main className="space-y-4 px-4 py-4">
        <p className="text-sm text-muted">{t.subtitle}</p>
        {error && <ErrorText>{error}</ErrorText>}
        {enrollments &&
          KINDS.map((kind) => (
            <KindCard
              key={kind}
              kind={kind}
              enrollment={enrollments.find((e) => e.kind === kind) ?? null}
              ensure={ensure}
              onChange={reload}
            />
          ))}
      </main>
      {sheet}
    </div>
  );
}

type Ensure = <T>(action: () => Promise<T>) => Promise<T>;

function messageFor(err: unknown): string | null {
  if (err instanceof StepUpCancelled) return null;
  const code = errorCode(err) as keyof typeof t.errors | null;
  return (code && t.errors[code]) || t.errors.generic;
}

function KindCard({
  kind,
  enrollment,
  ensure,
  onChange,
}: {
  kind: EnrollmentKind;
  enrollment: Enrollment | null;
  ensure: Ensure;
  onChange: () => Promise<void>;
}) {
  const status = enrollment?.status ?? "none";
  const open = enrollment && OPEN.has(enrollment.status);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function act(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await ensure(action);
      await onChange();
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setBusy(false);
      setConfirmRevoke(false);
    }
  }

  const Icon = kind === "voice" ? MicIcon : VideoIcon;
  return (
    <section className="card space-y-4 p-4">
      <div className="flex items-center gap-3">
        <span className="rounded-full bg-white/5 p-2 text-accent">
          <Icon />
        </span>
        <h2 className="flex-1 font-semibold">{t.kinds[kind]}</h2>
        <span className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted">
          {t.status[status]}
        </span>
      </div>

      {(!enrollment || !open) && (
        <StartEnrollment
          kind={kind}
          enrollment={enrollment}
          busy={busy}
          onStart={(v) => void act(() => startEnrollment(kind, v))}
        />
      )}
      {enrollment?.status === "collecting" && (
        <Collecting enrollment={enrollment} ensure={ensure} onChange={onChange} />
      )}
      {enrollment?.status === "pending_review" && (
        <p className="text-sm text-muted">{t.pendingBody}</p>
      )}
      {enrollment?.status === "processing" && (
        <p className="text-sm text-muted">{t.processingBody}</p>
      )}
      {enrollment?.status === "active" &&
        (kind === "voice" ? (
          <VoiceActive />
        ) : (
          <p className="text-sm text-muted">{t.activeFaceBody}</p>
        ))}

      {open && !confirmRevoke && (
        <SecondaryButton disabled={busy} onClick={() => setConfirmRevoke(true)}>
          {enrollment.status === "collecting" ? t.cancelEnrollment : t.revoke}
        </SecondaryButton>
      )}
      {open && confirmRevoke && (
        <div className="space-y-2 rounded-xl border border-red-400/40 bg-red-500/10 p-3">
          <p className="text-sm">{t.revokeConfirm}</p>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(() => revokeEnrollment(enrollment.id))}
              className="flex-1 rounded-xl bg-red-500 py-2 text-sm font-semibold"
            >
              {t.revokeYes}
            </button>
            <button
              type="button"
              onClick={() => setConfirmRevoke(false)}
              className="flex-1 rounded-xl border border-border py-2 text-sm"
            >
              {t.keep}
            </button>
          </div>
        </div>
      )}
      {error && <ErrorText>{error}</ErrorText>}
    </section>
  );
}

function StartEnrollment({
  kind,
  enrollment,
  busy,
  onStart,
}: {
  kind: EnrollmentKind;
  enrollment: Enrollment | null;
  busy: boolean;
  onStart: (version: string) => void;
}) {
  const [text, setText] = useState<ConsentText | null>(null);
  const [accepted, setAccepted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    consentText(kind)
      .then((c) => {
        if (!cancelled) setText(c);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [kind]);

  return (
    <div className="space-y-3">
      {enrollment?.status === "rejected" && enrollment.reject_reason && (
        <p className="text-sm text-amber">
          {t.rejectedBody}{" "}
          {t.reasons[enrollment.reject_reason as keyof typeof t.reasons] ??
            enrollment.reject_reason}
        </p>
      )}
      {text && (
        <p className="whitespace-pre-line text-sm leading-relaxed text-white/85">{text.summary}</p>
      )}
      <Checkbox checked={accepted} onChange={setAccepted}>
        {t.consentCheckbox}
      </Checkbox>
      <PrimaryButton
        disabled={!text || !accepted || busy}
        onClick={() => text && onStart(text.version)}
      >
        {enrollment ? t.tryAgain : t.start}
      </PrimaryButton>
    </div>
  );
}

function Collecting({
  enrollment,
  ensure,
  onChange,
}: {
  enrollment: Enrollment;
  ensure: Ensure;
  onChange: () => Promise<void>;
}) {
  const [passage, setPassage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const samples = enrollment.files.filter((f) => f.role === "sample");
  const consent = enrollment.files.find((f) => f.role === "consent_recording");
  const sampleKind: RecordingKind = enrollment.kind === "voice" ? "audio" : "video";

  useEffect(() => {
    if (enrollment.kind !== "voice") return;
    let cancelled = false;
    consentText("voice")
      .then((c) => {
        if (!cancelled) setPassage(c.reading_passage ?? null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [enrollment.kind]);

  async function upload(role: FileRole, blob: Blob, durationS?: number) {
    setBusy(true);
    setError(null);
    try {
      await uploadEnrollmentFile(enrollment.id, role, blob, durationS);
      await onChange();
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await ensure(action);
      await onChange();
    } catch (err) {
      setError(messageFor(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t.stepSamples}</h3>
        <p className="text-xs text-muted">
          {enrollment.kind === "voice" ? t.voiceSampleHint : t.faceSampleHint}
        </p>
        {passage && (
          <blockquote className="rounded-xl bg-white/5 p-3 text-sm leading-relaxed">
            {passage}
          </blockquote>
        )}
        <ul className="space-y-1">
          {samples.map((f, i) => (
            <li key={f.id} className="flex items-center justify-between text-xs text-muted">
              <span>
                {t.sample} {i + 1} ·{" "}
                {f.media_type.startsWith("image/") ? t.photo : `${f.duration_s ?? "?"} sn`}
              </span>
              <button
                type="button"
                disabled={busy}
                className="underline"
                onClick={() => void run(() => deleteEnrollmentFile(enrollment.id, f.id))}
              >
                {t.remove}
              </button>
            </li>
          ))}
        </ul>
        {samples.length < 5 && (
          <div className="space-y-2">
            {enrollment.kind === "face" && (
              <PhotoButton disabled={busy} onPicked={(file) => void upload("sample", file)} />
            )}
            <RecorderButton
              kind={sampleKind}
              maxSeconds={180}
              disabled={busy}
              onRecorded={(r) => void upload("sample", r.blob, r.durationS)}
            />
          </div>
        )}
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t.stepConsent}</h3>
        <p className="text-xs text-muted">{t.consentHint}</p>
        <blockquote className="rounded-xl border border-accent/40 bg-accent/10 p-3 text-[15px] leading-relaxed">
          {enrollment.consent_sentence}
        </blockquote>
        {consent && <p className="text-xs text-mint">{t.consentDone}</p>}
        <RecorderButton
          kind="video"
          maxSeconds={45}
          disabled={busy}
          label={consent ? t.retake : undefined}
          onRecorded={(r) => void upload("consent_recording", r.blob, r.durationS)}
        />
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-semibold">{t.stepSubmit}</h3>
        <p className="text-xs text-muted">{t.submitHint}</p>
        <PrimaryButton
          disabled={busy || samples.length === 0 || !consent}
          onClick={() => void run(() => submitEnrollment(enrollment.id))}
        >
          {busy ? t.uploading : t.submit}
        </PrimaryButton>
      </div>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}

/** Yüz fotoğrafı: telefonda ön kamerayı açar, bilgisayarda dosya seçtirir. Sunucu fotoğrafı
 * yeniden kodlar (konum bilgisi silinir); burada yalnızca tür kısıtlanır. */
function PhotoButton({
  disabled,
  onPicked,
}: {
  disabled: boolean;
  onPicked: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        capture="user"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) onPicked(file);
        }}
      />
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        className="w-full rounded-xl border border-border bg-white/5 py-3 text-sm font-semibold disabled:opacity-50"
      >
        {t.addPhoto}
      </button>
    </>
  );
}

function RecorderButton({
  kind,
  maxSeconds,
  disabled,
  label,
  onRecorded,
}: {
  kind: RecordingKind;
  maxSeconds: number;
  disabled: boolean;
  label?: string;
  onRecorded: (r: { blob: Blob; durationS: number }) => void;
}) {
  const recorder = useRecorder(kind, maxSeconds);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = recorder.stream;
  }, [recorder.stream]);

  async function start() {
    const result = await recorder.start();
    if (result) onRecorded(result);
  }

  return (
    <div className="space-y-2">
      {kind === "video" && recorder.stream && (
        <video ref={videoRef} autoPlay muted playsInline className="w-full rounded-xl bg-black" />
      )}
      {recorder.recording ? (
        <button
          type="button"
          onClick={recorder.stop}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-red-500 py-3 font-semibold"
        >
          <span className="h-2 w-2 animate-pulse rounded-full bg-white" />
          {t.recording} {recorder.elapsed} sn · {t.stop}
        </button>
      ) : (
        <button
          type="button"
          disabled={disabled}
          onClick={() => void start()}
          className="w-full rounded-xl border border-border bg-white/5 py-3 text-sm font-semibold disabled:opacity-50"
        >
          {label ?? t.record}
        </button>
      )}
      {recorder.error && <ErrorText>{t.errors[recorder.error]}</ErrorText>}
    </div>
  );
}

function VoiceActive() {
  const [sentences, setSentences] = useState<string[]>([]);
  const [playing, setPlaying] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    previewSentences()
      .then((s) => {
        if (!cancelled) setSentences(s);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function play(i: number) {
    setPlaying(i);
    setError(null);
    try {
      const url = await voicePreview(i);
      const audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPlaying(null);
      };
      await audio.play();
    } catch (err) {
      setError(messageFor(err));
      setPlaying(null);
    }
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted">{t.activeVoiceBody}</p>
      {sentences.map((s, i) => (
        <button
          key={s}
          type="button"
          disabled={playing !== null}
          onClick={() => void play(i)}
          className="flex w-full items-center gap-2 rounded-xl bg-white/5 px-3 py-2 text-left text-sm disabled:opacity-60"
        >
          <span className="text-accent">▶</span> {s}
        </button>
      ))}
      <Link href="/gorusme" className="block text-center text-sm text-accent underline">
        {t.callWithMine}
      </Link>
      {error && <ErrorText>{error}</ErrorText>}
    </div>
  );
}
