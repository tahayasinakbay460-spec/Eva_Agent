"use client";

import { useCallback, useEffect, useState } from "react";
import { me, tokenStore, type User } from "@/lib/api/client";

export type SessionState =
  | { status: "loading" }
  | { status: "needs_onboarding" }
  | { status: "ready"; user: User }
  | { status: "offline"; message: string };

/** Kayıtlı oturumu geri yükler; giriş ekranı yeni bir girişi `signedIn` ile bildirir. */
export function useSession(): {
  state: SessionState;
  signedIn: (user: User) => void;
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

  const signedIn = useCallback((user: User) => setState({ status: "ready", user }), []);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, signedIn, retry };
}
