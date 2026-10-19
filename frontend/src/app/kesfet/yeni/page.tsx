"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { CharacterForm } from "@/components/characters/CharacterForm";
import { ArrowLeft } from "@/components/icons";
import { ErrorText } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import { getCharacter, type Character } from "@/lib/api/client";

const t = messages().characters;

export default function NewCharacterPage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return (
    <Suspense fallback={null}>
      <CharacterEditor />
    </Suspense>
  );
}

/** ``?id=`` varsa o karakteri düzenler, yoksa yenisini oluşturur. */
function CharacterEditor() {
  const router = useRouter();
  const id = useSearchParams().get("id");
  const [initial, setInitial] = useState<Character | null>(null);
  const [loaded, setLoaded] = useState(!id);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    getCharacter(id)
      .then((c) => {
        if (cancelled) return;
        if (!c.is_mine) setError(t.loadError);
        else setInitial(c);
        setLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setError(t.loadError);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg-0/80 px-3 py-3 backdrop-blur-xl">
        <Link
          href="/kesfet"
          aria-label={t.back}
          className="rounded-full p-1 text-muted hover:text-white"
        >
          <ArrowLeft />
        </Link>
        <span className="flex-1 font-semibold">{id ? t.editTitle : t.newTitle}</span>
      </header>
      <main className="mx-auto max-w-md px-4 py-5">
        {error && <ErrorText>{error}</ErrorText>}
        {loaded && !error && (
          <CharacterForm initial={initial} onSaved={(c) => router.push(`/chat?karakter=${c.id}`)} />
        )}
      </main>
    </div>
  );
}
