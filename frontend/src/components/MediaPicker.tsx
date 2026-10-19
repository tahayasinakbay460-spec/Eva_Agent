"use client";

/**
 * EVA'nın sesi ve yüzü (görüşmeden önce). Ses ve yüz birbirinden bağımsız seçilir: hazır bir yüz
 * hazır bir sesle, kendi fotoğrafın hazır bir sesle ya da kendi klon sesinle eşleşebilir.
 * "Kendi" seçenekleri yalnızca kaydın onaylanınca görünür. Seçim sunucuda saklanır.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { CharacterFace } from "@/components/characters/CharacterFace";
import { messages } from "@/i18n";
import {
  OWN_MEDIA,
  PERSONA_MEDIA,
  avatarImageUrl,
  catalogVoicePreview,
  errorCode,
  mediaOptions,
  setMediaPreference,
  type CallMode,
  type MediaOptions,
} from "@/lib/api/client";

const t = messages().mediaPicker;

/** ``personaId`` verilirse o karakterin sesi/yüzü seçilir (karakterin kendi yüzü de seçenek). */
export function MediaPicker({
  mode,
  personaId,
  personaName,
}: {
  mode: CallMode;
  personaId?: string;
  personaName?: string;
}) {
  const [options, setOptions] = useState<MediaOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    mediaOptions(personaId)
      .then((o) => {
        if (!cancelled) setOptions(o);
      })
      .catch(() => {
        if (!cancelled) setError(t.loadFailed);
      });
    return () => {
      cancelled = true;
    };
  }, [personaId]);

  if (!options) return error ? <p className="text-xs text-red-300">{error}</p> : null;
  const { selected } = options;

  async function choose(voice: string, avatar: string) {
    if (!options) return;
    // Listede olmayan bir seçim (ör. bu sağlayıcıda hazır olmayan varsayılan yüz) gönderilmez;
    // boş = personanın varsayılanı.
    const usable = (key: string, list: { key: string }[], own: boolean) =>
      (key === OWN_MEDIA ? own : list.some((o) => o.key === key)) ? key : null;
    const avatarKey =
      avatar === PERSONA_MEDIA && options.persona_avatar
        ? avatar
        : usable(avatar, options.avatars, options.own_avatar);
    setError(null);
    try {
      setOptions(
        await setMediaPreference(
          { voice: usable(voice, options.voices, options.own_voice), avatar: avatarKey },
          personaId,
        ),
      );
    } catch (err) {
      const code = errorCode(err);
      setError(code === "no_active_voice" || code === "no_active_avatar" ? t.ownGone : t.failed);
    }
  }

  async function preview(key: string) {
    setPlaying(key);
    try {
      const url = await catalogVoicePreview(key);
      const audio = new Audio(url);
      audio.onended = () => {
        URL.revokeObjectURL(url);
        setPlaying(null);
      };
      await audio.play();
    } catch {
      setPlaying(null);
      setError(t.previewFailed);
    }
  }

  return (
    <div className="space-y-4 rounded-2xl bg-white/5 p-3">
      <section className="space-y-2">
        <h3 className="text-sm font-semibold">{personaId ? t.voiceGeneric : t.voice}</h3>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={t.voice}>
          {options.voices.map((v) => (
            <span
              key={v.key}
              className={`flex items-center overflow-hidden rounded-full border ${selected.voice === v.key ? "border-accent bg-accent/15" : "border-border"}`}
            >
              <button
                type="button"
                role="radio"
                aria-checked={selected.voice === v.key}
                onClick={() => void choose(v.key, selected.avatar)}
                className="py-1.5 pl-3 pr-1 text-sm"
              >
                {v.name}
              </button>
              <button
                type="button"
                aria-label={`${t.listen}: ${v.name}`}
                disabled={playing !== null}
                onClick={() => void preview(v.key)}
                className="px-2 py-1.5 text-xs text-accent disabled:opacity-50"
              >
                {playing === v.key ? "…" : "▶"}
              </button>
            </span>
          ))}
          {options.own_voice && (
            <button
              type="button"
              role="radio"
              aria-checked={selected.voice === OWN_MEDIA}
              onClick={() => void choose(OWN_MEDIA, selected.avatar)}
              className={`rounded-full border px-3 py-1.5 text-sm ${selected.voice === OWN_MEDIA ? "border-accent bg-accent/15" : "border-border"}`}
            >
              {t.ownVoice}
            </button>
          )}
        </div>
        {!options.own_voice && (
          <Link href="/profil/ses-yuz" className="block text-xs text-muted underline">
            {t.addOwnVoice}
          </Link>
        )}
      </section>

      {mode === "video" && (
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">{personaId ? t.faceGeneric : t.face}</h3>
          <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label={t.face}>
            {personaId && options.persona_avatar && (
              <button
                type="button"
                role="radio"
                aria-checked={selected.avatar === PERSONA_MEDIA}
                onClick={() => void choose(selected.voice, PERSONA_MEDIA)}
                className={`flex flex-col items-center gap-1 rounded-xl border p-2 text-xs ${selected.avatar === PERSONA_MEDIA ? "border-accent bg-accent/15" : "border-border"}`}
              >
                <CharacterFace
                  id={personaId}
                  name={personaName ?? ""}
                  hasFace
                  className="aspect-[2/3] w-full rounded-lg"
                />
                <span className="truncate">{personaName ?? t.personaFace}</span>
              </button>
            )}
            {options.avatars.map((a) => (
              <FaceCard
                key={a.key}
                label={a.name}
                imageKey={a.has_image ? a.key : null}
                active={selected.avatar === a.key}
                onClick={() => void choose(selected.voice, a.key)}
              />
            ))}
            {options.own_avatar && (
              <FaceCard
                label={t.ownFace}
                imageKey={null}
                active={selected.avatar === OWN_MEDIA}
                onClick={() => void choose(selected.voice, OWN_MEDIA)}
              />
            )}
          </div>
          {options.avatars.length === 0 && !options.own_avatar && !options.persona_avatar && (
            <p className="text-xs text-amber">{t.noFaces}</p>
          )}
          {!options.own_avatar && (
            <Link href="/profil/ses-yuz" className="block text-xs text-muted underline">
              {t.addOwnFace}
            </Link>
          )}
          {/* Kendi yüzü seçilip ses başka kaldıysa yalnızca öneri; seçim kullanıcıda kalır. */}
          {selected.avatar === OWN_MEDIA &&
            selected.voice !== OWN_MEDIA &&
            (options.own_voice ? (
              <p className="text-xs text-muted">{t.ownFaceVoiceHint}</p>
            ) : (
              <Link href="/profil/ses-yuz" className="block text-xs text-muted underline">
                {t.ownFaceVoiceAdd}
              </Link>
            ))}
        </section>
      )}
      {error && <p className="text-xs text-red-300">{error}</p>}
    </div>
  );
}

function FaceCard({
  label,
  imageKey,
  active,
  onClick,
}: {
  label: string;
  imageKey: string | null;
  active: boolean;
  onClick: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (!imageKey) return;
    let url: string | null = null;
    let cancelled = false;
    avatarImageUrl(imageKey)
      .then((u) => {
        url = u;
        if (!cancelled) setSrc(u);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [imageKey]);

  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`flex flex-col items-center gap-1 rounded-xl border p-2 text-xs ${active ? "border-accent bg-accent/15" : "border-border"}`}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element -- korumalı uçtan gelen geçici blob adresi
        <img src={src} alt="" className="aspect-[2/3] w-full rounded-lg object-cover" />
      ) : (
        <span className="flex aspect-[2/3] w-full items-center justify-center rounded-lg bg-white/10 text-lg font-semibold">
          {label.slice(0, 1)}
        </span>
      )}
      <span className="truncate">{label}</span>
    </button>
  );
}
