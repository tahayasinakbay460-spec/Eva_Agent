"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { CharacterFace } from "@/components/characters/CharacterFace";
import { ArrowLeft, HeartIcon, MicIcon, SendIcon } from "@/components/icons";
import { SaveMemorySheet } from "@/components/memories/SaveMemorySheet";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import {
  createConversation,
  getCharacter,
  listConversations,
  listMessages,
  listPersonas,
  newIdempotencyKey,
  sendMessage,
  type Character,
  type Message,
} from "@/lib/api/client";

const t = messages();
const CONVERSATION_KEY = "eva.conversation";

type Bubble = Pick<Message, "id" | "role" | "content" | "interrupted"> & { pending?: boolean };

export default function ChatPage() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  return (
    <Suspense fallback={null}>
      <Chat />
    </Suspense>
  );
}

/** ``?karakter=<id>`` verilirse o karakterle, yoksa EVA ile sohbet. */
function Chat() {
  const personaId = useSearchParams().get("karakter");
  // Her personanın son sohbeti ayrı hatırlanır.
  const storageKey = personaId ? `${CONVERSATION_KEY}.${personaId}` : CONVERSATION_KEY;
  const [character, setCharacter] = useState<Character | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Anıya çevrilmek üzere seçilen mesaj metni (pencere açıkken dolu).
  const [saving, setSaving] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!personaId) return;
    let cancelled = false;
    getCharacter(personaId)
      .then((c) => {
        if (!cancelled) setCharacter(c);
      })
      .catch(() => {
        if (!cancelled) setError(t.chat.errorFatal);
      });
    return () => {
      cancelled = true;
    };
  }, [personaId]);

  // Kayıtlı sohbete devam et; yoksa bu personayla en son sohbeti aç; o da yoksa yenisini oluştur.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      let id: string | null = null;
      try {
        id = localStorage.getItem(storageKey);
      } catch {
        /* localStorage okunamazsa görmezden gel */
      }
      try {
        if (!id) {
          const target =
            personaId ?? (await listPersonas()).find((p) => p.slug === "eva")?.id ?? null;
          const latest = (await listConversations()).find((c) => c.persona_id === target);
          id = latest?.id ?? (await createConversation(personaId ?? undefined)).id;
        }
        const history = await listMessages(id);
        if (cancelled) return;
        localStorage.setItem(storageKey, id);
        setConversationId(id);
        setBubbles(history);
      } catch {
        if (cancelled) return;
        // kayıtlı ID artık geçersiz olabilir (başka kullanıcı / silinmiş veritabanı): yeniden başla
        try {
          const created = await createConversation(personaId ?? undefined);
          localStorage.setItem(storageKey, created.id);
          setConversationId(created.id);
          setBubbles([]);
        } catch (err) {
          setError(String(err));
        }
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [personaId, storageKey]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [bubbles]);

  const send = useCallback(
    async (text: string) => {
      if (!conversationId || streaming) return;
      setError(null);
      setStreaming(true);
      const tempUserId = `tmp-u-${Date.now()}`;
      const tempAssistantId = `tmp-a-${Date.now()}`;
      setBubbles((b) => [
        ...b,
        { id: tempUserId, role: "user", content: text, interrupted: false },
        { id: tempAssistantId, role: "assistant", content: "", interrupted: false, pending: true },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      let assistantId = tempAssistantId;
      try {
        for await (const ev of sendMessage(
          conversationId,
          text,
          newIdempotencyKey(),
          controller.signal,
        )) {
          if (ev.type === "message_start") {
            assistantId = ev.data.assistant_message_id;
            setBubbles((b) =>
              b.map((m) =>
                m.id === tempUserId
                  ? { ...m, id: ev.data.user_message_id }
                  : m.id === tempAssistantId
                    ? { ...m, id: assistantId }
                    : m,
              ),
            );
          } else if (ev.type === "delta") {
            setBubbles((b) =>
              b.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + ev.text, pending: false } : m,
              ),
            );
          } else if (ev.type === "done") {
            setBubbles((b) =>
              b.map((m) =>
                m.id === assistantId
                  ? { ...m, pending: false, interrupted: ev.data.interrupted }
                  : m,
              ),
            );
          } else if (ev.type === "error") {
            setError(ev.data.retryable ? t.chat.errorRetryable : t.chat.errorFatal);
            setBubbles((b) => b.filter((m) => !(m.id === assistantId && m.content === "")));
          }
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(t.chat.errorRetryable);
          setBubbles((b) => b.filter((m) => !(m.id === assistantId && m.content === "")));
          console.error(err);
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [conversationId, streaming],
  );

  function submit(e: FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    // Sohbet yüklenene kadar taslağı tut; kullanıcının yazdığı hiçbir şey kaybolmasın.
    if (!text || !conversationId || streaming) return;
    setDraft("");
    void send(text);
  }

  async function startNew() {
    abortRef.current?.abort();
    const created = await createConversation(personaId ?? undefined);
    localStorage.setItem(storageKey, created.id);
    setConversationId(created.id);
    setBubbles([]);
    setError(null);
  }

  const title = personaId ? (character?.name ?? "") : "EVA";

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-border bg-bg-0/80 px-3 py-3 backdrop-blur-xl">
        <Link href="/" aria-label="Geri" className="rounded-full p-1 text-muted hover:text-white">
          <ArrowLeft />
        </Link>
        {character ? (
          <CharacterFace
            id={character.id}
            name={character.name}
            hasFace={character.has_face}
            className="h-9 w-9 rounded-full text-xs"
          />
        ) : (
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-xs font-bold">
            E
          </span>
        )}
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate font-semibold">{title}</span>
          <span className="flex items-center gap-1 text-[11px] text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-mint" />
            {streaming ? t.chat.typing : t.chat.online}
          </span>
        </span>
        {/* Her zaman görünen "AI simülasyonu" rozeti (CLAUDE.md §7): yapay zekâ bildirimi diyalogda değil, arayüzde yapılır. */}
        <span className="rounded-full border border-amber/40 bg-amber/10 px-2 py-0.5 text-[10px] font-medium text-amber">
          {t.app.aiBadge}
        </span>
        {personaId && (
          <Link
            href={`/gorusme?karakter=${personaId}`}
            aria-label={t.characters.call}
            className="rounded-full p-1 text-muted hover:text-white"
          >
            <MicIcon size={18} />
          </Link>
        )}
        <button
          onClick={startNew}
          title={t.chat.newConversation}
          aria-label={t.chat.newConversation}
          className="rounded-full p-1 text-lg leading-none text-muted hover:text-white"
        >
          +
        </button>
      </header>

      <main className="flex-1 space-y-2 px-4 py-4">
        {bubbles.length === 0 && (
          <p className="pt-20 text-center text-sm text-muted">
            {personaId ? t.chat.emptyCharacter : t.chat.empty}
          </p>
        )}
        {bubbles.map((m) => (
          <BubbleView key={m.id} bubble={m} onSaveAsMemory={setSaving} />
        ))}
        {error && <p className="text-center text-xs text-red-300">{error}</p>}
        {savedNotice && (
          <p role="status" className="text-center text-xs text-mint">
            {t.chat.savedAsMemory}{" "}
            <Link href="/anilar" className="underline">
              {t.chat.seeMemories}
            </Link>
          </p>
        )}
        <div ref={bottomRef} />
      </main>

      <form
        onSubmit={submit}
        className="sticky bottom-0 flex items-end gap-2 border-t border-border bg-bg-0/85 px-3 pb-[max(12px,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl"
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(e);
            }
          }}
          placeholder={personaId ? t.chat.placeholderCharacter : t.chat.placeholder}
          rows={1}
          maxLength={4000}
          className="max-h-32 min-h-[44px] flex-1 resize-none rounded-2xl border border-border bg-white/5 px-4 py-2.5 text-[15px] outline-none focus:border-accent"
        />
        <button
          type="submit"
          disabled={!conversationId || streaming || draft.trim().length === 0}
          aria-label={t.chat.send}
          className="glow-ring flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-white disabled:opacity-40"
        >
          <SendIcon size={18} />
        </button>
      </form>

      {saving !== null && (
        <SaveMemorySheet
          text={saving}
          onClose={() => setSaving(null)}
          onSaved={() => {
            setSaving(null);
            setSavedNotice(true);
          }}
        />
      )}
    </div>
  );
}

function BubbleView({
  bubble,
  onSaveAsMemory,
}: {
  bubble: Bubble;
  onSaveAsMemory: (text: string) => void;
}) {
  const mine = bubble.role === "user";
  // Sadece sunucuya kaydedilmiş kendi mesajların anıya çevrilebilir (geçici ID "tmp-" ile başlar).
  const canSave = mine && !bubble.id.startsWith("tmp-") && bubble.content.trim().length > 0;
  return (
    <div className={`flex flex-col ${mine ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[82%] whitespace-pre-wrap rounded-2xl px-3.5 py-2 text-[15px] leading-snug ${
          mine
            ? "rounded-br-sm bg-gradient-to-br from-accent to-accent-2 text-white"
            : "rounded-bl-sm bg-cyan/15 text-white"
        }`}
      >
        {bubble.pending ? (
          <span className="flex gap-1 py-1">
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-white/80" />
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-white/80" />
            <span className="typing-dot h-1.5 w-1.5 rounded-full bg-white/80" />
          </span>
        ) : (
          bubble.content
        )}
        {bubble.interrupted && (
          <span className="ml-1 text-[11px] text-white/60">{t.chat.interrupted}</span>
        )}
      </div>
      {canSave && (
        <button
          type="button"
          onClick={() => onSaveAsMemory(bubble.content)}
          className="mt-1 flex items-center gap-1 px-1 text-[11px] text-muted hover:text-white"
        >
          <HeartIcon size={12} /> {t.chat.saveAsMemory}
        </button>
      )}
    </div>
  );
}
