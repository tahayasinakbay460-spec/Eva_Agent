"use client";

/**
 * Seni vefat sonrası alıcı olarak belirlemiş kişiler (ADR 0011). Vefatını bildirmek için belge
 * yüklenir; ekip elle inceler, onaylansa bile sahibe 14 gün uyarı gider.
 */

import { useEffect, useState } from "react";
import { ErrorText } from "@/components/ui";
import { messages } from "@/i18n";
import { listHeirOf, reportDeath, type HeirOf } from "@/lib/api/client";

const t = messages().legacy;
const DOCUMENT_TYPES = "application/pdf,image/jpeg,image/png,image/webp";

export function HeirReports() {
  const [items, setItems] = useState<HeirOf[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listHeirOf()
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function upload(ownerId: string, file: File | undefined) {
    if (!file) return;
    setBusy(ownerId);
    setError(null);
    setNotice(null);
    try {
      await reportDeath(ownerId, file);
      setNotice(t.reportSent);
      setItems(await listHeirOf());
    } catch {
      setError(t.errors.generic);
    } finally {
      setBusy(null);
    }
  }

  if (items.length === 0) return null;
  return (
    <section className="space-y-3 rounded-2xl border border-amber/30 bg-amber/5 p-3">
      <h2 className="font-semibold">{t.reportTitle}</h2>
      <p className="text-xs text-muted">{t.reportHint}</p>
      <ul className="space-y-2">
        {items.map((h) => (
          <li key={h.owner_id} className="flex items-center justify-between gap-3 text-sm">
            <span className="font-semibold">{h.owner_name}</span>
            {h.open_report ? (
              <span className="text-xs text-amber">{t.reportOpen}</span>
            ) : (
              <label className="cursor-pointer rounded-full border border-border px-3 py-1 text-xs hover:border-amber">
                {busy === h.owner_id ? "…" : t.reportUpload}
                <input
                  type="file"
                  accept={DOCUMENT_TYPES}
                  className="hidden"
                  disabled={busy !== null}
                  onChange={(e) => void upload(h.owner_id, e.target.files?.[0])}
                />
              </label>
            )}
          </li>
        ))}
      </ul>
      {notice && <p className="text-xs text-mint">{notice}</p>}
      {error && <ErrorText>{error}</ErrorText>}
    </section>
  );
}
