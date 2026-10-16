"use client";

import { useCallback, useEffect, useState } from "react";
import {
  me,
  passkeyLogin,
  passkeySignUp,
  tokenStore,
  type SignUpForm,
  type User,
} from "@/lib/api/client";

export type SessionState =
  | { status: "loading" }
  | { status: "needs_onboarding" }
  | { status: "ready"; user: User }
  | { status: "offline"; message: string };

/** Restores the stored session, or lets the user sign up / sign in with a passkey. */
export function useSession(): {
  state: SessionState;
  signUp: (form: SignUpForm) => Promise<void>;
  signIn: () => Promise<void>;
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

  const signUp = useCallback(async (form: SignUpForm) => {
    const user = await passkeySignUp(form);
    setState({ status: "ready", user });
  }, []);

  const signIn = useCallback(async () => {
    const user = await passkeyLogin();
    setState({ status: "ready", user });
  }, []);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  return { state, signUp, signIn, retry };
}
