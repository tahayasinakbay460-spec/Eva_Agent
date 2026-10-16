"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { BottomNav } from "@/components/BottomNav";
import { ArrowLeft } from "@/components/icons";
import { MemoryCard } from "@/components/memories/MemoryCard";
import { MemoryForm } from "@/components/memories/MemoryForm";
import { ErrorText } from "@/components/ui";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  addMemory,
  ApiError,
  forgetMemory,
  listMemories,
  updateMemory,
  type Memory,
  type MemoryCreate,
  type MemoryKind,
} from "@/lib/api/client";

const t = messages().memories;

type Filter = "all" | MemoryKind;
// Form kapalı, yeni anı ekleniyor ya da belirli bir anı düzenleniyor.
type Editing = null | "new" | Memory;

export default function MemoriesPage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return <Memories />;
}

/** "EVA ne biliyor?" ekranı: anıları listeler, ekler, düzenler, unutturur (CLAUDE.md §6.4). */
function Memories() {
  const [filter, setFilter] = useState<Filter>("all");
  const [items, setItems] = useState<Memory[] | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (f: Filter) => {
    try {
      setItems(await listMemories(f === "all" ? undefined : f));
      setError(null);
    } catch {
      setError(t.loadError);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    listMemories(filter === "all" ? undefined : filter)
      .then((list) => {
        if (!cancelled) setItems(list);
      })
      .catch(() => {
        if (!cancelled) setError(t.loadError);
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  async function save(body: MemoryCreate) {
    setBusy(true);
    setError(null);
    try {
      if (editing === "new") await addMemory(body);
      else if (editing) await updateMemory(editing.id, body);
      setEditing(null);
      await load(filter);
    } catch (err) {
      setError(err instanceof ApiError && err.status === 409 ? t.limitError : t.saveError);
    } finally {
      setBusy(false);
    }
  }

  async function forget(memory: Memory) {
    setBusy(true);
    try {
      await forgetMemory(memory.id);
      setItems((list) => list?.filter((m) => m.id !== memory.id) ?? null);
    } catch {
      setError(t.saveError);
    } finally {
      setBusy(false);
    }
  }

  const tabs: [Filter, string][] = [
    ["all", t.tabAll],
    ["episode", t.tabEpisodes],
    ["fact", t.tabFacts],
  ];

  return (
    <>
      <main className="min-h-[calc(100dvh-72px)] space-y-4 px-4 pb-6 pt-4">
        <header className="flex items-start gap-3">
          <Link href="/" aria-label="Geri" className="mt-1 rounded-full p-1 text-muted">
            <ArrowLeft />
          </Link>
          <div>
            <h1 className="text-2xl font-semibold">{t.title}</h1>
            <p className="mt-1 text-sm text-muted">{t.subtitle}</p>
          </div>
        </header>

        {editing ? (
          <MemoryForm
            key={editing === "new" ? "new" : editing.id}
            initial={editing === "new" ? undefined : editing}
            busy={busy}
            error={error}
            onSave={(body) => void save(body)}
            onCancel={() => {
              setEditing(null);
              setError(null);
            }}
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditing("new")}
            className="w-full rounded-xl bg-gradient-to-r from-accent to-accent-2 py-3 font-semibold"
          >
            + {t.add}
          </button>
        )}

        <div role="tablist" className="flex gap-2">
          {tabs.map(([value, label]) => (
            <button
              key={value}
              role="tab"
              aria-selected={filter === value}
              onClick={() => {
                setFilter(value);
                setError(null);
              }}
              className={`rounded-full px-4 py-1.5 text-sm ${
                filter === value ? "bg-white/15 font-semibold" : "text-muted"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {!editing && error && <ErrorText>{error}</ErrorText>}

        {items !== null && items.length === 0 && (
          <p className="pt-8 text-center text-sm text-muted">
            {filter === "all" ? t.empty : t.emptyFiltered}
          </p>
        )}

        <ul className="space-y-3">
          {items?.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              busy={busy}
              onEdit={() => setEditing(memory)}
              onForget={() => void forget(memory)}
            />
          ))}
        </ul>
      </main>
      <BottomNav />
    </>
  );
}
