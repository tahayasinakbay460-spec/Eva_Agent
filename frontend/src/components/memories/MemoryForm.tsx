"use client";

import { useState, type FormEvent } from "react";
import { Checkbox, ErrorText, PrimaryButton, SecondaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import type { Memory, MemoryCreate, MemoryKind } from "@/lib/api/client";

const t = messages().memories;

type Emotion = NonNullable<MemoryCreate["emotion"]>;
const EMOTIONS = Object.keys(t.emotions) as Emotion[];

/** Hem yeni anı eklemek hem var olanı düzenlemek için aynı form. */
export function MemoryForm({
  initial,
  draft,
  busy,
  error,
  onSave,
  onCancel,
}: {
  initial?: Memory;
  /** Yeni anı için hazır metin (ör. sohbetteki bir mesajdan). */
  draft?: string;
  busy: boolean;
  error: string | null;
  onSave: (body: MemoryCreate) => void;
  onCancel: () => void;
}) {
  const [kind, setKind] = useState<MemoryKind>(initial?.kind ?? "episode");
  const [content, setContent] = useState(initial?.content ?? draft ?? "");
  const [date, setDate] = useState(initial?.occurred_on ?? "");
  const [people, setPeople] = useState((initial?.people ?? []).join(", "));
  const [emotion, setEmotion] = useState<Emotion | null>(initial?.emotion ?? null);
  const [sensitive, setSensitive] = useState(initial?.sensitivity === "sensitive");

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    onSave({
      kind,
      content: content.trim(),
      occurred_on: date || null,
      people: people
        .split(",")
        .map((p) => p.trim())
        .filter(Boolean)
        .slice(0, 20),
      emotion,
      sensitivity: sensitive ? "sensitive" : "normal",
    });
  }

  return (
    <form onSubmit={submit} className="card space-y-4 p-4">
      <div role="radiogroup" className="flex gap-1 rounded-xl border border-border bg-bg-0/60 p-1">
        {(["episode", "fact"] as const).map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={kind === value}
            onClick={() => setKind(value)}
            className={`flex-1 rounded-lg px-3 py-2 text-sm transition ${
              kind === value ? "bg-white/15 font-semibold text-white" : "text-muted"
            }`}
          >
            {value === "episode" ? t.kindEpisode : t.kindFact}
          </button>
        ))}
      </div>
      <p className="text-xs text-muted">
        {kind === "episode" ? t.kindEpisodeHint : t.kindFactHint}
      </p>

      <label className="block text-sm">
        <span className="text-muted">{t.contentLabel}</span>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t.contentPlaceholder}
          maxLength={2000}
          rows={3}
          autoFocus
          className="mt-1 w-full resize-none rounded-xl border border-border bg-bg-0/60 px-4 py-3 text-base outline-none focus:border-accent"
        />
      </label>

      {kind === "episode" && (
        <>
          <TextField
            label={t.dateLabel}
            type="date"
            value={date}
            max={new Date().toISOString().slice(0, 10)}
            onChange={(e) => setDate(e.target.value)}
          />
          <TextField
            label={t.peopleLabel}
            value={people}
            onChange={(e) => setPeople(e.target.value)}
            placeholder={t.peoplePlaceholder}
            maxLength={400}
          />
          <div className="text-sm">
            <span className="text-muted">{t.emotionLabel}</span>
            <div className="mt-2 flex flex-wrap gap-2">
              {EMOTIONS.map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={emotion === value}
                  onClick={() => setEmotion(emotion === value ? null : value)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    emotion === value
                      ? "border-accent bg-accent/20 text-white"
                      : "border-border text-muted"
                  }`}
                >
                  {t.emotions[value]}
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      <div>
        <Checkbox checked={sensitive} onChange={setSensitive}>
          {t.sensitive}
        </Checkbox>
        <p className="ml-7 mt-1 text-xs text-muted">{t.sensitiveHint}</p>
      </div>

      {error && <ErrorText>{error}</ErrorText>}
      <PrimaryButton type="submit" disabled={busy || !content.trim()}>
        {t.save}
      </PrimaryButton>
      <SecondaryButton onClick={onCancel} disabled={busy}>
        {t.cancel}
      </SecondaryButton>
    </form>
  );
}
