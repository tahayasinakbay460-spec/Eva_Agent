"use client";

/**
 * Miras — sahibin ekranı (Faz 5, ADR 0010): hazırlık durumu, kişilik taslağı, kapsam, önizleme,
 * yayın ve alıcılar. Ses ve yüz zorunlu; eksikse ses-yüz kaydına yönlendirilir.
 */

import Link from "next/link";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { ArrowLeft, MicIcon, SendIcon } from "@/components/icons";
import { DraftEditor } from "@/components/legacy/DraftEditor";
import { Recipients, legacyError } from "@/components/legacy/Recipients";
import { ScopeList } from "@/components/legacy/ScopeList";
import { StepUpCancelled, useStepUp } from "@/components/StepUpSheet";
import { ErrorText, PrimaryButton } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  getLegacyPersona,
  legacyConsentText,
  listLegacyGrants,
  listMemories,
  publishLegacy,
  synthesizeLegacy,
  type LegacyConsentText,
  type LegacyGrant,
  type LegacyPersona,
  type Memory,
} from "@/lib/api/client";

const t = messages().legacy;
const POLL_MS = 3000;

export default function LegacyPage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return <Legacy />;
}

function Legacy() {
  const [persona, setPersona] = useState<LegacyPersona | null>(null);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [grants, setGrants] = useState<LegacyGrant[]>([]);
  const [consent, setConsent] = useState<LegacyConsentText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const { ensure, sheet } = useStepUp();

  const reload = useCallback(async () => {
    const [p, m, g, c] = await Promise.all([
      getLegacyPersona(),
      listMemories(),
      listLegacyGrants(),
      legacyConsentText(),
    ]);
    setPersona(p);
    // Kapsam ekranı yalnızca EVA'yla oluşan anıları gösterir (Miras'ın ham maddesi).
    setMemories(m.filter((x) => x.persona_id !== p.id));
    setGrants(g);
    setConsent(c);
  }, []);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getLegacyPersona(), listMemories(), listLegacyGrants(), legacyConsentText()])
      .then(([p, m, g, c]) => {
        if (cancelled) return;
        setPersona(p);
        setMemories(m.filter((x) => x.persona_id !== p.id));
        setGrants(g);
        setConsent(c);
      })
      .catch(() => {
        if (!cancelled) setError(t.errors.generic);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Taslak işçide hazırlanırken durumu yokla.
  const pending = persona?.status === "pending";
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => {
      getLegacyPersona()
        .then((p) => {
          if (p.status !== "pending") setPersona(p);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pending]);

  async function synthesize() {
    setError(null);
    try {
      setPersona(await synthesizeLegacy());
    } catch (err) {
      setError(legacyError(err));
    }
  }

  async function publish() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const out = await ensure(() => publishLegacy());
      setNotice(t.published.replace("{version}", String(out.version)));
      await reload();
    } catch (err) {
      if (!(err instanceof StepUpCancelled)) setError(legacyError(err));
    } finally {
      setBusy(false);
    }
  }

  if (!persona) {
    return (
      <Shell>
        {error ? <ErrorText>{error}</ErrorText> : <p className="text-sm text-muted">…</p>}
      </Shell>
    );
  }

  const mediaReady = persona.voice_ready && persona.face_ready;
  const published = persona.published_version !== null;

  return (
    <Shell>
      <p className="text-sm text-muted">{t.subtitle}</p>
      {error && <ErrorText>{error}</ErrorText>}
      {notice && <p className="text-sm text-mint">{notice}</p>}

      <Section title={t.statusTitle}>
        <ul className="space-y-1 text-sm">
          <Status label={t.stepDraft} ok={persona.has_draft} />
          <Status label={t.stepVoice} ok={persona.voice_ready} />
          <Status label={t.stepFace} ok={persona.face_ready} />
          <li className="flex justify-between">
            <span>{t.stepPublished}</span>
            <span className={published ? "text-mint" : "text-muted"}>
              {published ? `v${persona.published_version}` : t.notYet}
            </span>
          </li>
          <li className="text-xs text-muted">
            {persona.included_memories} {t.memoriesIncluded}
          </li>
        </ul>
        {!mediaReady && (
          <Link href="/profil/ses-yuz" className="block text-sm text-accent underline">
            {t.addMedia}
          </Link>
        )}
      </Section>

      <Section title={t.draftTitle} hint={t.draftHint}>
        {persona.status === "pending" && <p className="text-sm text-amber">{t.synthesizing}</p>}
        {persona.status === "not_enough_data" && (
          <p className="text-sm text-amber">{t.notEnoughData}</p>
        )}
        {persona.status === "failed" && <p className="text-sm text-red-300">{t.synthesisFailed}</p>}
        <button
          type="button"
          disabled={pending}
          onClick={() => void synthesize()}
          className="rounded-full border border-border px-4 py-1.5 text-sm hover:border-accent disabled:opacity-50"
        >
          {persona.has_draft ? t.resynthesize : t.synthesize}
        </button>
        {(persona.has_draft || persona.status === "not_enough_data") && (
          // Yeni taslak gelince düzenleyici sıfırdan kurulsun (anahtar değişir).
          <DraftEditor
            key={`${persona.status}-${persona.identity.length}`}
            persona={persona}
            onSaved={setPersona}
          />
        )}
      </Section>

      <Section title={t.scopeTitle} hint={t.scopeHint}>
        <ScopeList
          memories={memories}
          onChanged={(m) => {
            setMemories((list) => list.map((x) => (x.id === m.id ? m : x)));
            void getLegacyPersona().then(setPersona);
          }}
        />
      </Section>

      {persona.has_draft && (
        <Section title={t.previewTitle} hint={t.previewHint}>
          <div className="flex gap-2">
            <Link
              href={`/chat?miras=${persona.id}`}
              className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-white/10 py-2 text-sm font-semibold"
            >
              <SendIcon size={14} /> {t.previewChat}
            </Link>
            {mediaReady && (
              <Link
                href={`/gorusme?miras=${persona.id}`}
                className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-gradient-to-r from-accent to-accent-2 py-2 text-sm font-semibold"
              >
                <MicIcon size={14} /> {t.previewCall}
              </Link>
            )}
          </div>
        </Section>
      )}

      <Section title={t.publishTitle} hint={t.publishHint}>
        <PrimaryButton
          disabled={busy || !persona.has_draft || !mediaReady}
          onClick={() => void publish()}
        >
          {published ? t.republish : t.publish}
        </PrimaryButton>
      </Section>

      <Section title={t.recipientsTitle} hint={t.recipientsHint}>
        <Recipients
          grants={grants}
          consent={consent}
          canSend={published && mediaReady}
          ensure={ensure}
          onChanged={() => void reload().catch(() => setError(t.errors.generic))}
        />
      </Section>
      {sheet}
    </Shell>
  );
}

function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg-0/80 px-3 py-3 backdrop-blur-xl">
        <Link
          href="/profil"
          aria-label="Geri"
          className="rounded-full p-1 text-muted hover:text-white"
        >
          <ArrowLeft />
        </Link>
        <span className="flex-1 font-semibold">{t.title}</span>
      </header>
      <main className="mx-auto max-w-md space-y-5 px-4 py-5">{children}</main>
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {hint && <p className="text-xs text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Status({ label, ok }: { label: string; ok: boolean }) {
  return (
    <li className="flex justify-between">
      <span>{label}</span>
      <span className={ok ? "text-mint" : "text-amber"}>{ok ? t.ready : t.missing}</span>
    </li>
  );
}
