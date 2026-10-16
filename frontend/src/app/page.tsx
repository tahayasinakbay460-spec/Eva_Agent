"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BottomNav } from "@/components/BottomNav";
import { Onboarding } from "@/components/Onboarding";
import {
  ChatIcon,
  ChevronRight,
  HeartIcon,
  InfinityIcon,
  LockIcon,
  MaskIcon,
  MicIcon,
  SmileIcon,
  VideoIcon,
} from "@/components/icons";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";
import { listConversations, listMessages, type Message } from "@/lib/api/client";

const t = messages();

export default function HomePage() {
  const { state, signUp, signIn, retry } = useSession();

  if (state.status === "loading") return <Splash />;
  if (state.status === "needs_onboarding") return <Onboarding signUp={signUp} signIn={signIn} />;
  if (state.status === "offline") return <Offline message={state.message} onRetry={retry} />;

  const firstName = state.user.display_name.split(" ")[0];
  const initials = state.user.display_name
    .split(" ")
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <>
      <main className="pb-2">
        <Hero firstName={firstName} fullName={state.user.display_name} initials={initials} />

        <section className="-mt-6 space-y-4 px-4">
          <MoodCard />
          <QuickActions />
          <div className="grid grid-cols-5 gap-3">
            <div className="col-span-3">
              <EvaMessageCard />
            </div>
            <div className="col-span-2">
              <DailyMessageCard />
            </div>
          </div>
          <StudioCard />
        </section>
      </main>
      <BottomNav />
    </>
  );
}

/* ---------------------------------------------------------------- hero */

function Hero({
  firstName,
  fullName,
  initials,
}: {
  firstName: string;
  fullName: string;
  initials: string;
}) {
  return (
    <header className="relative h-[330px] overflow-hidden">
      {/* abstract "portrait": warm glow + soft shapes stand in for the photo */}
      <div className="absolute inset-0 bg-[radial-gradient(70%_60%_at_65%_40%,#f59e8b_0%,#b15da8_35%,#4c2a84_65%,transparent_100%)] opacity-80" />
      <div className="absolute -right-10 top-10 h-64 w-64 rounded-full bg-[radial-gradient(circle,#ffd7b5_0%,#ff8ec7_40%,transparent_72%)] opacity-70 blur-sm" />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-bg-1 to-transparent" />

      <div className="relative flex items-center justify-between px-5 pt-5">
        <div>
          <div className="wordmark text-4xl leading-none">EVA</div>
          <div className="font-script text-xl text-accent/90">{t.app.tagline}</div>
        </div>
        <div className="flex items-center gap-3">
          <Link
            href="/profil"
            className="flex items-center gap-2 rounded-full bg-white/10 py-1 pl-1 pr-3 text-xs backdrop-blur"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-[11px] font-bold">
              {initials}
            </span>
            <span className="max-w-[90px] truncate">{fullName}</span>
            <ChevronRight size={14} className="rotate-90 text-muted" />
          </Link>
        </div>
      </div>

      <div className="relative mt-16 px-5">
        <div className="font-script text-4xl leading-none">
          {t.home.greeting}
          <br />
          {firstName}
          <span className="ml-2 text-accent">♡</span>
        </div>
        <p className="mt-2 max-w-[200px] text-sm text-white/85">{t.home.howAreYou}</p>
      </div>

      <Link
        href="/chat"
        className="absolute bottom-10 right-4 flex items-center gap-2 rounded-2xl border border-white/15 bg-black/35 px-3 py-2 text-xs backdrop-blur-md"
      >
        <Waveform />
        <span className="max-w-[110px] leading-tight">{t.home.readyToTalk}</span>
        <ChevronRight size={16} className="text-muted" />
      </Link>
    </header>
  );
}

function Waveform() {
  return (
    <span className="flex h-6 w-6 items-center justify-center gap-[2px] rounded-full bg-gradient-to-br from-accent to-accent-2">
      {[0.5, 0.9, 0.7, 1, 0.6].map((h, i) => (
        <span
          key={i}
          className="wave-bar w-[2px] rounded-full bg-white"
          style={{ height: `${h * 12}px`, animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </span>
  );
}

/* ---------------------------------------------------------------- cards */

function MoodCard() {
  return (
    <Link href="/analiz" className="card flex items-center gap-4 p-4">
      <span className="glow-ring flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-bg-0 text-mint">
        <SmileIcon size={30} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2 text-sm font-semibold">
          {t.home.moodTitle}
          <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-normal text-muted">
            {t.home.comingSoon}
          </span>
        </span>
        <span className="mt-0.5 block text-xs text-muted">{t.home.moodSubtitle}</span>
      </span>
      <ChevronRight className="text-muted" />
    </Link>
  );
}

function QuickActions() {
  const actions = [
    { href: "/chat", label: t.home.actions.chat, Icon: ChatIcon, color: "text-cyan" },
    { href: "/kesfet", label: t.home.actions.voice, Icon: MicIcon, color: "text-accent" },
    { href: "/kesfet", label: t.home.actions.video, Icon: VideoIcon, color: "text-cyan" },
    { href: "/kesfet", label: t.home.actions.memories, Icon: HeartIcon, color: "text-accent" },
    {
      href: "/kesfet",
      label: t.home.actions.legacy,
      Icon: InfinityIcon,
      color: "text-amber",
      locked: true,
    },
  ];
  return (
    <ul className="grid grid-cols-5 gap-2">
      {actions.map(({ href, label, Icon, color, locked }) => (
        <li key={label}>
          <Link
            href={href}
            className="card relative flex h-[76px] flex-col items-center justify-center gap-1.5 px-1 text-center"
          >
            <span className={`rounded-xl bg-white/5 p-1.5 ${color}`}>
              <Icon size={22} />
            </span>
            <span className="text-[10px] leading-tight text-white/90">{label}</span>
            {locked && (
              <span className="absolute right-1.5 top-1.5 text-muted">
                <LockIcon size={11} />
              </span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function EvaMessageCard() {
  const [last, setLast] = useState<Message | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [latest] = await listConversations();
        if (!latest) return;
        const msgs = await listMessages(latest.id);
        const reply = [...msgs].reverse().find((m) => m.role === "assistant");
        if (!cancelled && reply) setLast(reply);
      } catch {
        /* home still renders */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const time = last
    ? new Date(last.created_at).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
    : "";

  return (
    <Link href="/chat" className="card flex h-full flex-col p-3">
      <span className="flex items-center gap-2 text-xs">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-[10px] font-bold">
          E
        </span>
        <span className="font-semibold">EVA</span>
        <span className="h-1.5 w-1.5 rounded-full bg-mint" />
        <span className="ml-auto text-muted">{time}</span>
      </span>
      <span className="mt-2 line-clamp-4 rounded-2xl rounded-tl-sm bg-cyan/15 px-3 py-2 text-[12.5px] leading-snug">
        {last?.content ?? t.home.evaCardDefault}
      </span>
      <span className="mt-auto flex items-center justify-between pt-2 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <ChatIcon size={14} /> {t.home.actions.chat}
        </span>
        <span className="font-script text-base text-white/80">{t.home.evaCardFooter}</span>
      </span>
    </Link>
  );
}

function DailyMessageCard() {
  const quote = t.quotes[dayOfYear() % t.quotes.length];
  return (
    <div className="card relative flex h-full flex-col overflow-hidden p-3">
      <div className="absolute inset-0 bg-[radial-gradient(80%_50%_at_50%_100%,#f97316_0%,#7c3aed_55%,transparent_100%)] opacity-40" />
      <span className="relative text-xs font-semibold">{t.home.dailyMessage}</span>
      <span className="relative mt-auto font-script text-lg leading-tight text-white/90">
        “{quote}”
      </span>
      <ChevronRight size={16} className="relative ml-auto mt-1 text-muted" />
    </div>
  );
}

function StudioCard() {
  return (
    <Link href="/kesfet" className="card relative block overflow-hidden p-3">
      <div className="absolute inset-0 bg-[radial-gradient(90%_60%_at_80%_100%,#8b5cf6_0%,transparent_70%)] opacity-40" />
      <span className="relative flex items-center gap-2 text-sm font-semibold">
        <MaskIcon size={18} className="text-accent" /> {t.home.studioTitle}
      </span>
      <span className="relative mt-1 block text-[11px] leading-snug text-muted">
        {t.home.studioSubtitle}
      </span>
      <span className="relative mt-2 inline-block rounded-full bg-white/10 px-2 py-0.5 text-[10px] text-muted">
        {t.home.comingSoon}
      </span>
    </Link>
  );
}

/* ---------------------------------------------------------------- states */

function Splash() {
  return (
    <main className="flex min-h-dvh items-center justify-center">
      <div className="wordmark animate-pulse text-5xl">EVA</div>
    </main>
  );
}

function Offline({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <div className="wordmark text-4xl">EVA</div>
      <p className="text-sm text-muted">{t.chat.errorRetryable}</p>
      <code className="max-w-full truncate text-[10px] text-muted/60">{message}</code>
      <button
        onClick={onRetry}
        className="rounded-xl bg-gradient-to-r from-accent to-accent-2 px-5 py-2 text-sm font-semibold"
      >
        ↻
      </button>
    </main>
  );
}

function dayOfYear(): number {
  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 0);
  return Math.floor((now.getTime() - start.getTime()) / 86_400_000);
}
