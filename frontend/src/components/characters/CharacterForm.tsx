"use client";

/**
 * Karakter oluşturma / düzenleme formu. Yüz görseli (fotoğraf ya da çizim) isteğe bağlı;
 * yüklemeden önce kullanıcı hak ve 18+ beyanını onaylar. Ses hazır seslerden seçilir.
 */

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Checkbox, ErrorText, PrimaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import {
  ApiError,
  createCharacter,
  errorCode,
  mediaOptions,
  removeCharacterFace,
  updateCharacter,
  uploadCharacterFace,
  type Character,
  type CharacterIn,
  type MediaOption,
} from "@/lib/api/client";
import { CharacterFace } from "./CharacterFace";

const t = messages().characters;

const IMAGE_TYPES = "image/jpeg,image/png,image/webp";

export function CharacterForm({
  initial,
  onSaved,
}: {
  initial: Character | null;
  onSaved: (character: Character) => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [identity, setIdentity] = useState(initial?.identity ?? "");
  const [personality, setPersonality] = useState(initial?.personality ?? "");
  const [speakingStyle, setSpeakingStyle] = useState(initial?.speaking_style ?? "");
  const [exampleUser, setExampleUser] = useState(initial?.example_dialogs[0]?.user ?? "");
  const [examplePersona, setExamplePersona] = useState(initial?.example_dialogs[0]?.persona ?? "");
  const [timeAwareness, setTimeAwareness] = useState<CharacterIn["time_awareness"]>(
    initial?.time_awareness ?? "aware_of_present",
  );
  const [visibility, setVisibility] = useState<CharacterIn["visibility"]>(
    initial?.visibility ?? "public",
  );
  const [voiceKey, setVoiceKey] = useState<string | null>(initial?.voice_key ?? null);
  const [voices, setVoices] = useState<MediaOption[]>([]);
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [removeFace, setRemoveFace] = useState(false);
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    mediaOptions()
      .then((o) => {
        if (!cancelled) setVoices(o.voices);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Önizleme adresi yeni dosya seçilince ya da sayfadan çıkınca bırakılır.
  const previewRef = useRef<string | null>(null);
  useEffect(
    () => () => {
      if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    },
    [],
  );

  function pickPhoto(file: File | null) {
    if (previewRef.current) URL.revokeObjectURL(previewRef.current);
    previewRef.current = file ? URL.createObjectURL(file) : null;
    setPreview(previewRef.current);
    setPhoto(file);
  }

  const required = name.trim() && identity.trim() && personality.trim();
  const canSave = Boolean(required) && !busy && (!photo || rights);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!canSave) return;
    setBusy(true);
    setError(null);
    const body: CharacterIn = {
      name: name.trim(),
      identity: identity.trim(),
      personality: personality.trim(),
      speaking_style: speakingStyle.trim(),
      example_dialogs:
        exampleUser.trim() && examplePersona.trim()
          ? [{ user: exampleUser.trim(), persona: examplePersona.trim() }]
          : [],
      time_awareness: timeAwareness,
      visibility,
      voice_key: voiceKey,
    };
    let saved: Character;
    try {
      saved = initial ? await updateCharacter(initial.id, body) : await createCharacter(body);
    } catch (err) {
      const code = errorCode(err);
      if (code?.startsWith("blocked_")) setError(t.blockedName);
      else setError(err instanceof ApiError && err.status === 409 ? t.limitError : t.saveError);
      setBusy(false);
      return;
    }
    try {
      if (photo) saved = await uploadCharacterFace(saved.id, photo);
      else if (removeFace && saved.has_face) saved = await removeCharacterFace(saved.id);
    } catch {
      // Karakter kaydedildi; yalnızca görsel olmadı. Düzenleme ekranında tekrar denenebilir.
      setError(t.faceError);
      setBusy(false);
      return;
    }
    setBusy(false);
    onSaved(saved);
  }

  const showExistingFace = initial?.has_face && !photo && !removeFace;

  return (
    <form onSubmit={submit} className="space-y-4">
      <section className="space-y-2">
        <span className="text-sm text-muted">{t.face}</span>
        <div className="flex items-center gap-3">
          {preview ? (
            // eslint-disable-next-line @next/next/no-img-element -- yerel önizleme (blob adresi)
            <img src={preview} alt="" className="h-20 w-20 rounded-2xl object-cover" />
          ) : showExistingFace && initial ? (
            <CharacterFace
              id={initial.id}
              name={initial.name}
              hasFace
              className="h-20 w-20 rounded-2xl"
            />
          ) : (
            <span className="flex h-20 w-20 items-center justify-center rounded-2xl bg-white/10 text-2xl font-semibold">
              {name.slice(0, 1).toUpperCase() || "?"}
            </span>
          )}
          <div className="flex flex-col items-start gap-1">
            <label className="cursor-pointer rounded-full border border-border px-3 py-1.5 text-sm hover:border-accent">
              {preview || showExistingFace ? t.changePhoto : t.pickPhoto}
              <input
                type="file"
                accept={IMAGE_TYPES}
                className="hidden"
                onChange={(e) => {
                  pickPhoto(e.target.files?.[0] ?? null);
                  setRemoveFace(false);
                }}
              />
            </label>
            {(preview || showExistingFace) && (
              <button
                type="button"
                onClick={() => {
                  pickPhoto(null);
                  setRemoveFace(true);
                }}
                className="px-1 text-xs text-muted underline"
              >
                {t.removePhoto}
              </button>
            )}
          </div>
        </div>
        {photo && (
          <Checkbox checked={rights} onChange={setRights}>
            {t.rights}
          </Checkbox>
        )}
      </section>

      <TextField
        label={t.name}
        placeholder={t.namePlaceholder}
        value={name}
        maxLength={80}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <TextArea
        label={t.identity}
        placeholder={t.identityPlaceholder}
        value={identity}
        maxLength={2000}
        onChange={setIdentity}
      />
      <TextArea
        label={t.personality}
        placeholder={t.personalityPlaceholder}
        value={personality}
        maxLength={4000}
        onChange={setPersonality}
      />
      <TextArea
        label={t.speakingStyle}
        placeholder={t.speakingStylePlaceholder}
        value={speakingStyle}
        maxLength={4000}
        onChange={setSpeakingStyle}
      />

      <section className="space-y-2 rounded-2xl bg-white/5 p-3">
        <span className="text-sm text-muted">{t.exampleTitle}</span>
        <TextField
          label={t.exampleUser}
          value={exampleUser}
          maxLength={500}
          onChange={(e) => setExampleUser(e.target.value)}
        />
        <TextField
          label={t.examplePersona}
          value={examplePersona}
          maxLength={1000}
          onChange={(e) => setExamplePersona(e.target.value)}
        />
      </section>

      <Choice label={t.timeAwareness}>
        <Pill
          active={timeAwareness === "aware_of_present"}
          onClick={() => setTimeAwareness("aware_of_present")}
        >
          {t.awareOfPresent}
        </Pill>
        <Pill active={timeAwareness === "in_era"} onClick={() => setTimeAwareness("in_era")}>
          {t.inEra}
        </Pill>
      </Choice>

      <Choice label={t.visibility}>
        <Pill active={visibility === "public"} onClick={() => setVisibility("public")}>
          {t.public}
        </Pill>
        <Pill active={visibility === "private"} onClick={() => setVisibility("private")}>
          {t.onlyMe}
        </Pill>
      </Choice>

      <Choice label={t.voice}>
        <Pill active={voiceKey === null} onClick={() => setVoiceKey(null)}>
          {t.defaultVoice}
        </Pill>
        {voices.map((v) => (
          <Pill key={v.key} active={voiceKey === v.key} onClick={() => setVoiceKey(v.key)}>
            {v.name}
          </Pill>
        ))}
      </Choice>

      {error && <ErrorText>{error}</ErrorText>}
      <PrimaryButton type="submit" disabled={!canSave}>
        {busy ? t.saving : t.save}
      </PrimaryButton>
    </form>
  );
}

function TextArea({
  label,
  value,
  onChange,
  placeholder,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  maxLength: number;
}) {
  return (
    <label className="block text-sm">
      <span className="text-muted">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        maxLength={maxLength}
        rows={3}
        className="mt-1 w-full resize-y rounded-xl border border-border bg-bg-0/60 px-4 py-3 text-base outline-none focus:border-accent"
      />
    </label>
  );
}

function Choice({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <span className="text-sm text-muted">{label}</span>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
        {children}
      </div>
    </section>
  );
}

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-sm ${active ? "border-accent bg-accent/15" : "border-border"}`}
    >
      {children}
    </button>
  );
}
