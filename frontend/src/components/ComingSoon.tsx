import Link from "next/link";
import { BottomNav } from "@/components/BottomNav";
import { SparkIcon } from "@/components/icons";
import { messages } from "@/i18n";

const t = messages();

export function ComingSoon({ title }: { title: string }) {
  return (
    <>
      <main className="flex min-h-[calc(100dvh-72px)] flex-col items-center justify-center gap-3 px-6 text-center">
        <span className="rounded-full bg-white/5 p-4 text-accent">
          <SparkIcon size={32} />
        </span>
        <h1 className="text-2xl font-semibold">{title}</h1>
        <p className="text-sm text-muted">{t.comingSoon.body}</p>
        <Link
          href="/chat"
          className="mt-2 rounded-xl bg-gradient-to-r from-accent to-accent-2 px-5 py-2 text-sm font-semibold"
        >
          {t.home.actions.chat}
        </Link>
      </main>
      <BottomNav />
    </>
  );
}
