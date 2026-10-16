"use client";

import Link from "next/link";
import { AuthScreen } from "@/components/auth/AuthScreen";
import { BottomNav } from "@/components/BottomNav";
import { ChevronRight, LockIcon, MicIcon, UserIcon } from "@/components/icons";
import { useSession } from "@/hooks/useSession";
import { messages } from "@/i18n";

const t = messages();

export default function Page() {
  const { state, signedIn } = useSession();
  if (state.status === "needs_onboarding") return <AuthScreen onSignedIn={signedIn} />;
  if (state.status !== "ready") return null;
  const user = state.user;

  const items = [
    {
      href: "/profil/ses-yuz",
      title: t.profile.mediaTitle,
      body: t.profile.mediaBody,
      Icon: UserIcon,
    },
    { href: "/gorusme", title: t.profile.callTitle, body: t.profile.callBody, Icon: MicIcon },
    ...(user.role === "admin"
      ? [
          {
            href: "/yonetim",
            title: t.profile.reviewTitle,
            body: t.profile.reviewBody,
            Icon: LockIcon,
          },
        ]
      : []),
  ];

  return (
    <>
      <main className="min-h-[calc(100dvh-72px)] space-y-4 px-4 py-6">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-lg font-bold">
            {user.display_name.slice(0, 1).toUpperCase()}
          </span>
          <div>
            <h1 className="text-xl font-semibold">{user.display_name}</h1>
            {user.email && <p className="text-xs text-muted">{user.email}</p>}
          </div>
        </div>
        {items.map(({ href, title, body, Icon }) => (
          <Link key={href} href={href} className="card flex items-center gap-3 p-4">
            <span className="rounded-full bg-white/5 p-2 text-accent">
              <Icon />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block font-semibold">{title}</span>
              <span className="block text-xs text-muted">{body}</span>
            </span>
            <ChevronRight className="text-muted" />
          </Link>
        ))}
      </main>
      <BottomNav />
    </>
  );
}
