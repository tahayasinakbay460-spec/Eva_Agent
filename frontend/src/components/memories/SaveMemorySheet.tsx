"use client";

import { useState } from "react";
import { MemoryForm } from "@/components/memories/MemoryForm";
import { messages } from "@/i18n";
import { addMemory, ApiError, type MemoryCreate } from "@/lib/api/client";

const t = messages().memories;

/**
 * Sohbetteki bir mesajı anıya çevirmek için alttan açılan pencere (CLAUDE.md §6.2:
 * "Bunu anı olarak kaydet" denince kısa bir onay alınıp kaydedilir). Metin hazır gelir,
 * kullanıcı düzeltip kaydeder; hiçbir şey onaysız kaydedilmez.
 */
export function SaveMemorySheet({
  text,
  onClose,
  onSaved,
}: {
  text: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(body: MemoryCreate) {
    setBusy(true);
    setError(null);
    try {
      await addMemory(body);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t.limitError : t.saveError);
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t.add}
      className="fixed inset-0 z-30 flex items-end justify-center bg-black/60 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="max-h-[90dvh] w-full max-w-[430px] overflow-y-auto p-3">
        <MemoryForm
          draft={text.slice(0, 2000)}
          busy={busy}
          error={error}
          onSave={(body) => void save(body)}
          onCancel={onClose}
        />
      </div>
    </div>
  );
}
