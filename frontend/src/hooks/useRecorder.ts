"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type RecordingKind = "audio" | "video";
export type Recording = { blob: Blob; durationS: number };

// Tarayıcının desteklediği ilk biçim seçilir (Chrome/Firefox: WebM, Safari: MP4).
const MIME_CANDIDATES: Record<RecordingKind, string[]> = {
  audio: ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"],
  video: ["video/webm;codecs=vp8,opus", "video/webm", "video/mp4"],
};

function pickMime(kind: RecordingKind): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIME_CANDIDATES[kind].find((m) => MediaRecorder.isTypeSupported(m));
}

/**
 * Mikrofon (ve video için kamera) kaydı. Kayıt yalnızca tarayıcıda tutulur; yükleme
 * çağıranın işi. `maxSeconds` dolunca kayıt kendiliğinden durur.
 */
export function useRecorder(kind: RecordingKind, maxSeconds: number) {
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<"camera" | "unsupported" | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const resolveRef = useRef<((r: Recording | null) => void) | null>(null);
  const startedAt = useRef(0);

  const release = useCallback(() => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
    recorderRef.current = null;
    setStream(null);
    setRecording(false);
  }, []);

  useEffect(() => release, [release]);

  useEffect(() => {
    if (!recording) return;
    const id = setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt.current) / 1000);
      setElapsed(seconds);
      if (seconds >= maxSeconds) recorderRef.current?.stop();
    }, 250);
    return () => clearInterval(id);
  }, [recording, maxSeconds]);

  /** Kaydı başlatır; durunca (stop ya da süre dolunca) kayıt döner. İptal edilirse null. */
  const start = useCallback(async (): Promise<Recording | null> => {
    setError(null);
    const mime = pickMime(kind);
    if (!mime || !navigator.mediaDevices?.getUserMedia) {
      setError("unsupported");
      return null;
    }
    let media: MediaStream;
    try {
      media = await navigator.mediaDevices.getUserMedia(
        kind === "video"
          ? { audio: true, video: { width: { ideal: 1280 }, height: { ideal: 720 } } }
          : { audio: { echoCancellation: true, noiseSuppression: true } },
      );
    } catch {
      setError("camera");
      return null;
    }
    const recorder = new MediaRecorder(media, {
      mimeType: mime,
      audioBitsPerSecond: 128_000,
      videoBitsPerSecond: kind === "video" ? 1_500_000 : undefined,
    });
    const chunks: Blob[] = [];
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    const done = new Promise<Recording | null>((resolve) => {
      resolveRef.current = resolve;
      recorder.onstop = () => {
        const durationS = (Date.now() - startedAt.current) / 1000;
        const type = mime.split(";")[0];
        release();
        resolve(chunks.length ? { blob: new Blob(chunks, { type }), durationS } : null);
      };
    });
    recorderRef.current = recorder;
    startedAt.current = Date.now();
    setElapsed(0);
    setStream(kind === "video" ? media : null);
    recorder.start(1000);
    setRecording(true);
    return done;
  }, [kind, release]);

  const stop = useCallback(() => recorderRef.current?.stop(), []);

  return { start, stop, recording, elapsed, stream, error };
}
