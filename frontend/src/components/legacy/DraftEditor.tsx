"use client";

/** Miras kişilik taslağı: işçinin çıkardığı metni sahibi okur ve düzeltir (ADR 0010, adım 3). */

import { useState, type FormEvent } from "react";
import { ErrorText, PrimaryButton, TextField } from "@/components/ui";
import { messages } from "@/i18n";
import { updateLegacyDraft, type LegacyDraft, type LegacyPersona } from "@/lib/api/client";

const t = messages().legacy;

const EMPTY_EXAMPLE = { user: "", persona: "" };

export function DraftEditor({
  persona,
  onSaved,
}: {
  persona: LegacyPersona;
  onSaved: (persona: LegacyPersona) => void;
}) {
  const [identity, setIdentity] = useState(persona.identity);
  const [personality, setPersonality] = useState(persona.personality);
  const [speakingStyle, setSpeakingStyle] = useState(persona.speaking_style);
  const [examples, setExamples] = useState(
    persona.example_dialogs.length ? persona.example_dialogs : [EMPTY_EXAMPLE],
  );
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const canSave = Boolean(identity.trim() && personality.trim() && speakingStyle.trim()) && !busy;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!canSave) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    const body: LegacyDraft = {
      identity: identity.trim(),
      personality: personality.trim(),
      speaking_style: speakingStyle.trim(),
      example_dialogs: examples
        .map((x) => ({ user: x.user.trim(), persona: x.persona.trim() }))
        .filter((x) => x.user && x.persona),
    };
    try {
      onSaved(await updateLegacyDraft(body));
      setNotice(t.saved);
    } catch {
      setError(t.errors.generic);
    } finally {
      setBusy(false);
    }
  }

  function setExample(i: number, key: "user" | "persona", value: string) {
    setExamples((list) => list.map((x, j) => (j === i ? { ...x, [key]: value } : x)));
  }

  return (
    <form onSubmit={save} className="space-y-3">
      <Area label={t.identity} value={identity} onChange={setIdentity} max={2000} />
      <Area label={t.personality} value={personality} onChange={setPersonality} max={4000} />
      <Area label={t.speakingStyle} value={speakingStyle} onChange={setSpeakingStyle} max={4000} />
      <section className="space-y-2 rounded-2xl bg-white/5 p-3">
        <span className="text-sm text-muted">{t.examples}</span>
        {examples.map((x, i) => (
          <div key={i} className="space-y-2 border-b border-border pb-2 last:border-0">
            <TextField
              label={t.exampleUser}
              value={x.user}
              maxLength={500}
              onChange={(e) => setExample(i, "user", e.target.value)}
            />
            <TextField
              label={t.examplePersona}
              value={x.persona}
              maxLength={1000}
              onChange={(e) => setExample(i, "persona", e.target.value)}
            />
          </div>
        ))}
        {examples.length < 10 && (
          <button
            type="button"
            onClick={() => setExamples((list) => [...list, EMPTY_EXAMPLE])}
            className="text-sm text-accent"
          >
            +
          </button>
        )}
      </section>
      {error && <ErrorText>{error}</ErrorText>}
      {notice && <p className="text-xs text-mint">{notice}</p>}
      <PrimaryButton type="submit" disabled={!canSave}>
        {t.saveDraft}
      </PrimaryButton>
    </form>
  );
}

function Area({
  label,
  value,
  onChange,
  max,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  max: number;
}) {
  return (
    <label className="block text-sm">
      <span className="text-muted">{label}</span>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={max}
        rows={4}
        className="mt-1 w-full resize-y rounded-xl border border-border bg-bg-0/60 px-4 py-3 text-base outline-none focus:border-accent"
      />
    </label>
  );
}
