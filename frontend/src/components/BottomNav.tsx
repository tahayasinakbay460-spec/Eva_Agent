"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { messages } from "@/i18n";
import { ChartIcon, CompassIcon, HomeIcon, UserIcon } from "./icons";

const t = messages();

const items = [
  { href: "/", label: t.nav.home, Icon: HomeIcon },
  { href: "/analiz", label: t.nav.insights, Icon: ChartIcon },
  { href: "/chat", label: null, Icon: null },
  { href: "/kesfet", label: t.nav.explore, Icon: CompassIcon },
  { href: "/profil", label: t.nav.profile, Icon: UserIcon },
] as const;

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      aria-label="Ana menü"
      className="sticky bottom-0 z-20 mt-6 border-t border-border bg-bg-0/80 px-4 pb-[max(10px,env(safe-area-inset-bottom))] pt-2 backdrop-blur-xl"
    >
      <ul className="grid grid-cols-5 items-end">
        {items.map(({ href, label, Icon }) => {
          if (!Icon) {
            return (
              <li key={href} className="flex justify-center">
                <Link
                  href={href}
                  aria-label={t.app.name}
                  className="glow-ring -mt-7 flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-sm font-extrabold tracking-wider text-white shadow-lg"
                >
                  EVA
                </Link>
              </li>
            );
          }
          const active = pathname === href;
          return (
            <li key={href} className="flex justify-center">
              <Link
                href={href}
                className={`flex flex-col items-center gap-1 px-2 py-1 text-[11px] ${
                  active ? "text-white" : "text-muted"
                }`}
              >
                <Icon size={22} />
                {label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
