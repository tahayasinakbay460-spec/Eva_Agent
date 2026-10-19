"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { BottomNav } from "@/components/BottomNav";
import { CharacterFace } from "@/components/characters/CharacterFace";
import { MicIcon, SendIcon } from "@/components/icons";
import { ErrorText, Heading } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  deleteCharacter,
  listCharacters,
  listSharedLegacies,
  type Character,
  type SharedLegacy,
} from "@/lib/api/client";

const t = messages().characters;

type Scope = "public" | "mine";

export default function ExplorePage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return <Explore />;
}

/** Karakter Stüdyosu (Faz 4): herkese açık karakterler ve kullanıcının kendi karakterleri. */
function Explore() {
  const [scope, setScope] = useState<Scope>("public");
  const [items, setItems] = useState<Character[] | null>(null);
  // Başkalarının seninle paylaştığı Miras personaları (anahtarla açılmış, hâlâ açık olanlar).
  const [shared, setShared] = useState<SharedLegacy[]>([]);

  useEffect(() => {
    let cancelled = false;
    listSharedLegacies()
      .then((list) => {
        if (!cancelled) setShared(list.filter((s) => s.status === "active"));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);
  const [error, setError] = useState<string | null>(null);
  // Silme iki dokunuşla: ilki onay ister.
  const [confirming, setConfirming] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCharacters(scope)
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch(() => {
        if (!cancelled) setError(t.loadError);
      });
    return () => {
      cancelled = true;
    };
  }, [scope]);

  async function remove(id: string) {
    if (confirming !== id) {
      setConfirming(id);
      return;
    }
    setConfirming(null);
    try {
      await deleteCharacter(id);
      setItems((list) => list?.filter((c) => c.id !== id) ?? null);
    } catch {
      setError(t.loadError);
    }
  }

  return (
    <>
      <main className="min-h-[calc(100dvh-72px)] space-y-4 px-4 pb-4 pt-6">
        <div className="flex items-start justify-between gap-3">
          <Heading title={t.title} body={t.subtitle} />
          <Link
            href="/kesfet/yeni"
            className="shrink-0 rounded-full bg-gradient-to-r from-accent to-accent-2 px-4 py-2 text-sm font-semibold"
          >
            + {t.create}
          </Link>
        </div>

        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-white/5 p-1" role="radiogroup">
          {(["public", "mine"] as const).map((s) => (
            <button
              key={s}
              type="button"
              role="radio"
              aria-checked={scope === s}
              onClick={() => {
                setScope(s);
                setItems(null);
              }}
              className={`rounded-xl py-2 text-sm font-semibold ${scope === s ? "bg-white/15" : "text-muted"}`}
            >
              {s === "public" ? t.tabPublic : t.tabMine}
            </button>
          ))}
        </div>

        {error && <ErrorText>{error}</ErrorText>}

        {scope === "mine" && shared.length > 0 && (
          <section className="space-y-2">
            <h2 className="text-sm font-semibold">{t.sharedWithYou}</h2>
            <ul className="grid grid-cols-2 gap-3">
              {shared.map((s) => (
                <li
                  key={s.access_id}
                  className="flex flex-col gap-2 rounded-2xl border border-accent/30 bg-accent/10 p-3"
                >
                  <span className="flex items-center gap-2 font-semibold">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-xs">
                      {s.owner_name.slice(0, 1).toUpperCase()}
                    </span>
                    <span className="truncate">{s.owner_name}</span>
                  </span>
                  <span className="text-[11px] text-muted">{t.sharedBadge}</span>
                  <div className="flex gap-2">
                    <Link
                      href={`/chat?miras=${s.persona_id}`}
                      className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-white/10 py-1.5 text-xs font-semibold"
                    >
                      <SendIcon size={12} /> {t.chat}
                    </Link>
                    <Link
                      href={`/gorusme?miras=${s.persona_id}`}
                      className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-gradient-to-r from-accent to-accent-2 py-1.5 text-xs font-semibold"
                    >
                      <MicIcon size={12} /> {t.call}
                    </Link>
                  </div>
                </li>
              ))}
            </ul>
            <Link href="/miras/anahtar" className="block text-xs text-muted underline">
              {t.manageShared}
            </Link>
          </section>
        )}

        {items && items.length === 0 && !(scope === "mine" && shared.length > 0) && (
          <p className="pt-10 text-center text-sm text-muted">
            {scope === "public" ? t.empty : t.emptyMine}
          </p>
        )}

        <ul className="grid grid-cols-2 gap-3">
          {items?.map((c) => (
            <li key={c.id} className="flex flex-col overflow-hidden rounded-2xl bg-white/5">
              <CharacterFace
                id={c.id}
                name={c.name}
                hasFace={c.has_face}
                catalogAvatar={c.catalog_avatar}
                className="aspect-square w-full text-3xl"
              />
              <div className="flex flex-1 flex-col gap-1 p-3">
                <span className="flex items-center gap-2 font-semibold">
                  <span className="truncate">{c.name}</span>
                  {c.builtin && (
                    <span className="rounded-full bg-accent/20 px-1.5 text-[10px] text-accent">
                      {t.builtin}
                    </span>
                  )}
                  {c.visibility === "private" && (
                    <span className="rounded-full bg-white/10 px-1.5 text-[10px] text-muted">
                      {t.private}
                    </span>
                  )}
                </span>
                <span className="line-clamp-2 text-xs text-muted">{c.identity}</span>
                <div className="mt-auto flex gap-2 pt-2">
                  <Link
                    href={`/chat?karakter=${c.id}`}
                    className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-white/10 py-1.5 text-xs font-semibold"
                  >
                    <SendIcon size={12} /> {t.chat}
                  </Link>
                  <Link
                    href={`/gorusme?karakter=${c.id}`}
                    className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-gradient-to-r from-accent to-accent-2 py-1.5 text-xs font-semibold"
                  >
                    <MicIcon size={12} /> {t.call}
                  </Link>
                </div>
                {c.is_mine && (
                  <div className="flex justify-between pt-1 text-[11px] text-muted">
                    <Link href={`/kesfet/yeni?id=${c.id}`} className="underline">
                      {t.edit}
                    </Link>
                    <button
                      type="button"
                      onClick={() => void remove(c.id)}
                      className={confirming === c.id ? "text-red-300" : "underline"}
                    >
                      {confirming === c.id ? t.deleteConfirm : t.delete}
                    </button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </main>
      <BottomNav />
    </>
  );
}
