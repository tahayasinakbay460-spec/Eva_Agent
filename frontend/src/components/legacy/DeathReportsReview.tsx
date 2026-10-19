"use client";

/**
 * Yönetici: vefat bildirimlerinin elle incelenmesi (ADR 0011). Belgeyi açmak ve karar vermek
 * adım-yukarı doğrulama ister; her açılış denetim kaydına yazılır. Onay Miras'ı hemen açmaz:
 * sahibe 14 günlük uyarı süreci başlar.
 */

import { useEffect, useState } from "react";
import { StepUpCancelled } from "@/components/StepUpSheet";
import { ErrorText } from "@/components/ui";
import { messages } from "@/i18n";
import {
  deathReportDocumentUrl,
  decideDeathReport,
  listDeathReports,
  type DeathReport,
} from "@/lib/api/client";

const t = messages().review;

export function DeathReportsReview({
  ensure,
}: {
  ensure: <T>(action: () => Promise<T>) => Promise<T>;
}) {
  const [items, setItems] = useState<DeathReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listDeathReports()
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  async function open(id: string) {
    setError(null);
    try {
      const url = await ensure(() => deathReportDocumentUrl(id));
      window.open(url, "_blank", "noopener");
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(t.deathReportError);
    }
  }

  async function decide(id: string, decision: "approve" | "reject") {
    setError(null);
    try {
      await ensure(() => decideDeathReport(id, decision));
      setNotice(decision === "approve" ? t.deathReportApproved : t.decided);
      setItems(await listDeathReports());
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(t.deathReportError);
    }
  }

  if (items.length === 0 && !notice) return null;
  return (
    <section className="space-y-3">
      <h2 className="font-semibold">{t.deathReportsTitle}</h2>
      <p className="text-xs text-muted">{t.deathReportsHint}</p>
      {items.map((r) => (
        <div key={r.id} className="space-y-2 rounded-2xl bg-white/5 p-3 text-sm">
          <p>
            <span className="font-semibold">{r.owner_name}</span> ·{" "}
            <span className="text-muted">
              {t.deathReportBy} {r.reporter_name}
            </span>
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void open(r.id)}
              className="rounded-full border border-border px-3 py-1 text-xs"
            >
              {t.deathReportOpen}
            </button>
            <button
              type="button"
              onClick={() => void decide(r.id, "approve")}
              className="rounded-full bg-amber/20 px-3 py-1 text-xs text-amber"
            >
              {t.deathReportApprove}
            </button>
            <button
              type="button"
              onClick={() => void decide(r.id, "reject")}
              className="rounded-full border border-border px-3 py-1 text-xs text-muted"
            >
              {t.deathReportReject}
            </button>
          </div>
        </div>
      ))}
      {notice && <p className="text-xs text-mint">{notice}</p>}
      {error && <ErrorText>{error}</ErrorText>}
    </section>
  );
}
