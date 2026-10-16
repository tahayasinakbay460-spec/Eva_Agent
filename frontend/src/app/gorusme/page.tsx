"use client";

/**
 * Sesli / görüntülü görüşme ekranı (Faz 2-3). "EVA'yı ara"ya basınca backend bir görüşme açar ve kısa
 * ömürlü bir LiveKit token'ı verir; tarayıcı odaya bağlanıp mikrofonu açar, EVA'nın ajanı
 * da aynı odaya katılır. Ses doğrudan tarayıcı ↔ LiveKit arasında akar.
 *
 * Ekranda: EVA'nın durumu (dinliyor / düşünüyor / konuşuyor), canlı yazıya dökülen konuşma,
 * kalan süre, mikrofon ve kapat düğmeleri; görüşme bitince gecikme panosu. Görüntülü
 * görüşmede EVA'nın avatarı (LiveAvatar) odaya katılıp yüz videosunu yayınlar. "Kendi sesimle"
 * seçilirse EVA, kullanıcının rızalı klon sesiyle (ve yüzüyle) konuşur (önizleme, Faz 3).
 */

import Link from "next/link";
import {
  ConnectionState,
  Room,
  RoomEvent,
  Track,
  type Participant,
  type RemoteTrack,
} from "livekit-client";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { ArrowLeft, MicIcon, MicOffIcon, PhoneOffIcon, VideoIcon } from "@/components/icons";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  ApiError,
  endCall,
  errorCode,
  latencyReport,
  startCall,
  type Call,
  type CallMode,
  type LatencyReport,
} from "@/lib/api/client";

const t = messages();

type Phase = "idle" | "connecting" | "in_call" | "ended";
type AgentState = "initializing" | "listening" | "thinking" | "speaking" | "idle";
type Line = { id: string; who: "user" | "eva"; text: string; final: boolean };

export default function CallPage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return (
    <Suspense fallback={null}>
      <CallFromUrl />
    </Suspense>
  );
}

/** `?mine=1`: "Ses ve yüz" ekranındaki "Kendi sesimle EVA'yı ara" bağlantısı. */
function CallFromUrl() {
  const params = useSearchParams();
  return <VoiceCall initialMine={params.get("mine") === "1"} />;
}

function VoiceCall({ initialMine }: { initialMine: boolean }) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [mode, setMode] = useState<CallMode>("voice");
  const [useMine, setUseMine] = useState(initialMine);
  const [hasVideo, setHasVideo] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [muted, setMuted] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null);
  const [deadline, setDeadline] = useState<number | null>(null);
  const [report, setReport] = useState<LatencyReport | null>(null);
  const roomRef = useRef<Room | null>(null);
  const callRef = useRef<Call | null>(null);
  const audioHost = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const loadReport = useCallback(async () => {
    try {
      setReport(await latencyReport());
    } catch {
      /* pano yüklenemezse görüşme yine de çalışır */
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    latencyReport()
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch(() => {
        /* pano yüklenemezse görüşme yine de çalışır */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [lines]);

  const hangUp = useCallback(async () => {
    const room = roomRef.current;
    const call = callRef.current;
    roomRef.current = null;
    callRef.current = null;
    await room?.disconnect();
    if (call) {
      try {
        await endCall(call.call_id);
      } catch {
        /* ajan da görüşmeyi kapatır; burada hata önemli değil */
      }
    }
    setPhase("ended");
    setAgentState(null);
    setSecondsLeft(null);
    setDeadline(null);
    // Son turun süreleri yazılsın diye biraz bekleyip panoyu yenile.
    setTimeout(() => void loadReport(), 1500);
  }, [loadReport]);

  // Sayfadan çıkılırsa görüşmeyi kapat.
  useEffect(() => {
    return () => {
      void roomRef.current?.disconnect();
    };
  }, []);

  // Kalan süre sayacı; süre bitince kapat (ajan da kapatır, bu sadece ekran için).
  useEffect(() => {
    if (phase !== "in_call" || deadline === null) return;
    const id = setInterval(() => {
      const left = Math.max(0, Math.round((deadline - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left === 0) void hangUp();
    }, 1000);
    return () => clearInterval(id);
  }, [phase, deadline, hangUp]);

  async function start() {
    setError(null);
    setLines([]);
    setHasVideo(false);
    setPhase("connecting");
    let call: Call;
    try {
      call = await startCall(mode, useMine);
    } catch (err) {
      setPhase("idle");
      const code = errorCode(err);
      if (err instanceof ApiError && err.status === 503) setError(t.call.notConfigured);
      else if (err instanceof ApiError && err.status === 429) setError(t.call.quotaExceeded);
      else if (code === "no_active_voice") setError(t.call.noActiveVoice);
      else if (code === "no_active_avatar") setError(t.call.noActiveAvatar);
      else setError(t.call.failed);
      return;
    }
    callRef.current = call;

    const room = new Room({ adaptiveStream: true, dynacast: true });
    roomRef.current = room;
    room
      .on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach();
          audioHost.current?.appendChild(el);
        } else if (track.kind === Track.Kind.Video && videoRef.current) {
          // Avatarın yüz videosu (EVA adına yayın yapan avatar katılımcısından gelir).
          track.attach(videoRef.current);
          setHasVideo(true);
        }
      })
      .on(RoomEvent.TrackUnsubscribed, (track: RemoteTrack) => {
        track.detach().forEach((el) => el.remove());
      })
      .on(RoomEvent.ParticipantAttributesChanged, (_changed, participant: Participant) => {
        const value = participant.attributes["lk.agent.state"];
        if (value) setAgentState(value as AgentState);
      })
      .on(RoomEvent.Disconnected, () => {
        if (roomRef.current === room) void hangUp();
      });

    // Canlı yazı: ajan hem kullanıcının hem EVA'nın sözlerini "lk.transcription" akışıyla yollar.
    room.registerTextStreamHandler("lk.transcription", async (reader, participantInfo) => {
      const info = reader.info;
      const segmentId = info.attributes?.["lk.segment_id"] ?? info.id;
      const who: Line["who"] =
        participantInfo.identity === room.localParticipant.identity ? "user" : "eva";
      const final = info.attributes?.["lk.transcription_final"] === "true";
      let text = "";
      try {
        for await (const chunk of reader) {
          text += chunk;
          const snapshot = text;
          setLines((prev) => upsertLine(prev, { id: segmentId, who, text: snapshot, final }));
        }
      } catch {
        /* görüşme kapanırken yarım kalan yazı akışı: gelen kadarı ekranda kalır */
      }
    });

    try {
      await room.connect(call.livekit_url, call.token);
      await room.localParticipant.setMicrophoneEnabled(true);
      await room.startAudio();
    } catch (err) {
      await room.disconnect();
      roomRef.current = null;
      setPhase("idle");
      const denied = err instanceof Error && /Permission|NotAllowed/i.test(err.name + err.message);
      setError(denied ? t.call.micDenied : t.call.failed);
      return;
    }
    if (room.state === ConnectionState.Connected) {
      setPhase("in_call");
      setMuted(false);
      setSecondsLeft(call.max_duration_s);
      setDeadline(Date.now() + call.max_duration_s * 1000);
    }
  }

  async function toggleMute() {
    const room = roomRef.current;
    if (!room) return;
    await room.localParticipant.setMicrophoneEnabled(muted);
    setMuted(!muted);
  }

  const statusText =
    phase === "connecting"
      ? t.call.connecting
      : agentState === "speaking"
        ? t.call.speaking
        : agentState === "thinking"
          ? t.call.thinking
          : agentState === "listening"
            ? t.call.listening
            : t.call.waitingAgent;

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg-0/80 px-3 py-3 backdrop-blur-xl">
        <Link href="/" aria-label="Geri" className="rounded-full p-1 text-muted hover:text-white">
          <ArrowLeft />
        </Link>
        <span className="flex-1 font-semibold">
          {mode === "video" ? t.call.titleVideo : t.call.title}
        </span>
        {/* Her zaman görünen "AI simülasyonu" rozeti (CLAUDE.md §7). */}
        <span className="rounded-full border border-amber/40 bg-amber/10 px-2 py-0.5 text-[10px] font-medium text-amber">
          {t.app.aiBadge}
        </span>
      </header>

      <main className="flex flex-1 flex-col items-center px-4 py-6">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          className={`w-full max-w-md rounded-2xl bg-black ${hasVideo && phase === "in_call" ? "" : "hidden"}`}
        />
        {!(hasVideo && phase === "in_call") && (
          <Orb active={phase === "in_call"} speaking={agentState === "speaking"} />
        )}
        {mode === "video" && phase === "in_call" && !hasVideo && agentState && (
          <p className="mt-2 max-w-md text-center text-xs text-amber">{t.call.mockAvatar}</p>
        )}
        <p className="mt-4 text-lg font-semibold">EVA</p>
        {phase === "in_call" || phase === "connecting" ? (
          <p className="text-sm text-muted" aria-live="polite">
            {muted ? t.call.muted : statusText}
            {secondsLeft !== null && (
              <span className="ml-2 tabular-nums">
                · {formatTime(secondsLeft)} {t.call.timeLeft}
              </span>
            )}
          </p>
        ) : (
          phase === "ended" && <p className="text-sm text-muted">{t.call.ended}</p>
        )}

        {lines.length > 0 && (
          <div className="mt-6 w-full max-w-md flex-1 space-y-2 overflow-y-auto">
            {lines.map((line) => (
              <p
                key={line.id}
                className={`text-[15px] leading-snug ${line.who === "user" ? "text-right text-white/80" : "text-cyan"} ${line.final ? "" : "opacity-70"}`}
              >
                <span className="mr-1 text-[11px] text-muted">
                  {line.who === "user" ? t.call.you : "EVA"}
                </span>
                {line.text}
              </p>
            ))}
            <div ref={bottomRef} />
          </div>
        )}

        {error && (
          <p role="alert" className="mt-6 max-w-md text-center text-sm text-red-300">
            {error}
          </p>
        )}

        {(phase === "idle" || phase === "ended") && (
          <div className="mt-8 w-full max-w-md space-y-4">
            <div className="grid grid-cols-2 gap-2 rounded-2xl bg-white/5 p-1" role="radiogroup">
              {(["voice", "video"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={mode === m}
                  onClick={() => setMode(m)}
                  className={`rounded-xl py-2 text-sm font-semibold ${mode === m ? "bg-white/15" : "text-muted"}`}
                >
                  {m === "voice" ? t.call.modeVoice : t.call.modeVideo}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-sm text-muted">
              <input
                type="checkbox"
                checked={useMine}
                onChange={(e) => setUseMine(e.target.checked)}
                className="h-4 w-4 accent-[var(--color-accent)]"
              />
              {t.call.useMine}
            </label>
            <button
              type="button"
              onClick={start}
              className="glow-ring flex w-full items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-accent to-accent-2 py-4 text-lg font-semibold text-white"
            >
              {mode === "video" ? <VideoIcon /> : <MicIcon />}{" "}
              {phase === "ended" ? t.call.callAgain : t.call.start}
            </button>
            <p className="text-center text-xs text-muted">{t.call.startHint}</p>
            {phase === "ended" && (
              <Link href="/chat" className="block text-center text-sm text-muted underline">
                {t.call.backToChat}
              </Link>
            )}
            <LatencyBoard report={report} />
          </div>
        )}
      </main>

      {phase === "in_call" && (
        <footer className="sticky bottom-0 flex justify-center gap-6 border-t border-border bg-bg-0/85 px-3 pb-[max(16px,env(safe-area-inset-bottom))] pt-4 backdrop-blur-xl">
          <button
            type="button"
            onClick={toggleMute}
            aria-label={muted ? t.call.unmute : t.call.mute}
            className={`flex h-14 w-14 items-center justify-center rounded-full border border-border ${muted ? "bg-white text-bg-0" : "bg-white/10 text-white"}`}
          >
            {muted ? <MicOffIcon /> : <MicIcon />}
          </button>
          <button
            type="button"
            onClick={() => void hangUp()}
            aria-label={t.call.hangUp}
            className="flex h-14 w-14 items-center justify-center rounded-full bg-red-500 text-white"
          >
            <PhoneOffIcon />
          </button>
        </footer>
      )}
      <div ref={audioHost} hidden />
    </div>
  );
}

function upsertLine(lines: Line[], next: Line): Line[] {
  const i = lines.findIndex((l) => l.id === next.id);
  if (i === -1) return [...lines, next].slice(-30);
  const copy = lines.slice();
  copy[i] = next;
  return copy;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

function Orb({ active, speaking }: { active: boolean; speaking: boolean }) {
  return (
    <div className="relative mt-6 flex h-40 w-40 items-center justify-center">
      <span
        className={`absolute inset-0 rounded-full bg-gradient-to-br from-accent to-accent-2 opacity-30 blur-2xl transition-transform duration-500 ${speaking ? "scale-125" : active ? "scale-100" : "scale-75"}`}
      />
      <span
        className={`relative flex h-32 w-32 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-4xl font-bold transition-transform duration-300 ${speaking ? "scale-110" : "scale-100"}`}
      >
        E
      </span>
    </div>
  );
}

const STAGE_ORDER = [
  "e2e_ms",
  "end_of_turn_ms",
  "stt_final_ms",
  "llm_ttft_ms",
  "tts_ttfb_ms",
] as const;

function LatencyBoard({ report }: { report: LatencyReport | null }) {
  const e2e = report?.stages["e2e_ms"];
  const target = report?.targets_ms["e2e_ms"]?.["p50"] ?? 800;
  return (
    <section className="card p-4">
      <h2 className="text-sm font-semibold">{t.call.latencyTitle}</h2>
      <p className="mt-0.5 text-xs text-muted">{t.call.latencyHint}</p>
      {!e2e || e2e.count === 0 ? (
        <p className="mt-3 text-xs text-muted">{t.call.latencyEmpty}</p>
      ) : (
        <table className="mt-3 w-full text-xs">
          <thead className="text-muted">
            <tr>
              <th className="text-left font-normal" />
              <th className="text-right font-normal">p50</th>
              <th className="text-right font-normal">p95</th>
            </tr>
          </thead>
          <tbody>
            {STAGE_ORDER.map((stage) => {
              const s = report?.stages[stage];
              if (!s || s.count === 0) return null;
              const slow = stage === "e2e_ms" && (s.p50 ?? 0) > target;
              return (
                <tr key={stage} className={stage === "e2e_ms" ? "font-semibold" : ""}>
                  <td className="py-0.5">{t.call.stages[stage]}</td>
                  <td className={`text-right tabular-nums ${slow ? "text-red-300" : ""}`}>
                    {fmtMs(s.p50)}
                  </td>
                  <td className="text-right tabular-nums">{fmtMs(s.p95)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function fmtMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "–";
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} sn` : `${Math.round(ms)} ms`;
}
