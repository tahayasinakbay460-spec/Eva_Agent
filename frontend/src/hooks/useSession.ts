"use client";

import { useCallback, useEffect, useState } from "react";
import { devLogin, me, tokenStore, type User } from "@/lib/api/client";

const ONBOARDED_KEY = "eva.onboarded";

export type SessionState =
  | { status: "loading" }
  | { status: "needs_onboarding" }
  | { status: "ready"; user: User }
  | { status: "offline"; message: string };

/** Dev session: restores the stored token, or asks for a name and performs dev-login. */
export function useSession(): {
  state: SessionState;
  onboard: (displayName: string) => Promise<void>;
  retry: () => void;
} {
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!tokenStore.get()) {
        setState({ status: "needs_onboarding" });
        return;
      }
      try {
        const user = await me();
        if (!cancelled) setState({ status: "ready", user });
      } catch (err) {
        if (cancelled) return;
        const status = (err as { status?: number }).status;
        if (status === 401) {
          tokenStore.clear();
          setState({ status: "needs_onboarding" });
        } else {
          setState({ status: "offline", message: String(err) });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const onboard = useCallback(async (displayName: string) => {
    const handle = toHandle(displayName);
    const user = await devLogin(handle, displayName.trim());
    try {
      localStorage.setItem(ONBOARDED_KEY, "1");
    } catch {
      /* ignore */
    }
    setState({ status: "ready", user });
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, onboard, retry };
}

function toHandle(name: string): string {
  const ascii = name
    .toLowerCase()
    .replace(/ı/g, "i")
    .replace(/ğ/g, "g")
    .replace(/ü/g, "u")
    .replace(/ş/g, "s")
    .replace(/ö/g, "o")
    .replace(/ç/g, "c")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9_.-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const base = ascii.length >= 2 ? ascii : "user";
  return `${base}-${Math.random().toString(36).slice(2, 6)}`.slice(0, 64);
}
