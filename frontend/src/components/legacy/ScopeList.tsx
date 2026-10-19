"use client";

/** Hangi anılar Miras'a girsin (ADR 0010, adım 4). Hassas anılar başta hariçtir. */

import { useState } from "react";
import { messages } from "@/i18n";
import { setMemoryLegacyScope, type Memory } from "@/lib/api/client";

const t = messages().legacy;

export function ScopeList({
  memories,
  onChanged,
}: {
  memories: Memory[];
  onChanged: (memory: Memory) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState(false);

  async function toggle(m: Memory) {
    setBusy(m.id);
    setError(false);
    try {
      onChanged(
        await setMemoryLegacyScope(m.id, m.legacy_scope === "included" ? "excluded" : "included"),
      );
    } catch {
      setError(true);
    } finally {
      setBusy(null);
    }
  }

  if (memories.length === 0) return <p className="text-sm text-muted">{t.noMemories}</p>;
  return (
    <ul className="space-y-2">
      {memories.map((m) => {
        const included = m.legacy_scope === "included";
        return (
          <li key={m.id} className="flex items-start gap-3 rounded-xl bg-white/5 p-3">
            <span className="min-w-0 flex-1 text-sm">
              {m.content}
              {m.sensitivity === "sensitive" && (
                <span className="ml-2 rounded-full bg-amber/15 px-1.5 text-[10px] text-amber">
                  {t.sensitive}
                </span>
              )}
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={included}
              disabled={busy === m.id}
              onClick={() => void toggle(m)}
              className={`shrink-0 rounded-full border px-3 py-1 text-xs ${included ? "border-accent bg-accent/15" : "border-border text-muted"}`}
            >
              {included ? t.included : t.excluded}
            </button>
          </li>
        );
      })}
      {error && <li className="text-xs text-red-300">{t.errors.generic}</li>}
    </ul>
  );
}
