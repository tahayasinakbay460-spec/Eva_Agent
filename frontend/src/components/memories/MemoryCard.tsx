"use client";

import { useState } from "react";
import { messages } from "@/i18n";
import type { Memory } from "@/lib/api/client";

const t = messages().memories;

function formatDate(iso: string): string {
  // "2025-07-20" -> "20 Temmuz 2025". Saat dilimi kaymasın diye öğlen 12'ye sabitliyoruz.
  return new Date(`${iso}T12:00:00`).toLocaleDateString("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** Tek bir anı: içerik, ayrıntılar, kaynak etiketi; Düzenle ve (onaylı) Unut düğmeleri. */
export function MemoryCard({
  memory,
  busy,
  onEdit,
  onForget,
}: {
  memory: Memory;
  busy: boolean;
  onEdit: () => void;
  onForget: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const details = [
    memory.occurred_on ? formatDate(memory.occurred_on) : null,
    memory.people.length ? memory.people.join(", ") : null,
    memory.emotion ? t.emotions[memory.emotion] : null,
  ].filter(Boolean);

  return (
    <li className="card space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <span className="rounded-full bg-white/10 px-2 py-0.5 text-muted">
          {memory.kind === "episode" ? t.kindEpisode : t.kindFact}
        </span>
        <span className="rounded-full bg-cyan/15 px-2 py-0.5 text-cyan">
          {memory.source === "auto" ? t.sourceAuto : t.sourceUser}
        </span>
        {memory.sensitivity === "sensitive" && (
          <span className="rounded-full bg-amber/15 px-2 py-0.5 text-amber">
            {t.sensitiveBadge}
          </span>
        )}
      </div>
      <p className="whitespace-pre-wrap text-[15px] leading-snug">{memory.content}</p>
      {details.length > 0 && <p className="text-xs text-muted">{details.join(" · ")}</p>}

      {confirming ? (
        <div className="space-y-2 rounded-xl border border-red-400/30 bg-red-400/10 p-3">
          <p className="text-xs text-red-200">{t.forgetConfirm}</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onForget}
              disabled={busy}
              className="flex-1 rounded-lg bg-red-500/80 py-2 text-sm font-semibold disabled:opacity-50"
            >
              {t.forgetYes}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={busy}
              className="flex-1 rounded-lg bg-white/10 py-2 text-sm"
            >
              {t.cancel}
            </button>
          </div>
        </div>
      ) : (
        <div className="flex justify-end gap-4 pt-1 text-xs">
          <button type="button" onClick={onEdit} disabled={busy} className="text-muted">
            {t.edit}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(true)}
            disabled={busy}
            className="text-red-300"
          >
            {t.forget}
          </button>
        </div>
      )}
    </li>
  );
}
