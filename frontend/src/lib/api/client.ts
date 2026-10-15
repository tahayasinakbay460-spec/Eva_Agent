/**
 * Thin typed client over the EVA API. Types come from `schema.d.ts`, which is generated
 * from the backend's OpenAPI schema (`npm run gen-client`) - never edit it by hand.
 *
 * Dev-only: the access token lives in localStorage. Production auth (passkey + MFA,
 * httpOnly cookies) replaces `devLogin` and `tokenStore`; call sites stay the same.
 */

import { readSSE } from "../sse";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type User = Schemas["UserOut"];
export type Conversation = Schemas["ConversationOut"];
export type Message = Schemas["MessageOut"];
export type SSEDone = Schemas["SSEDone"];
export type SSEError = Schemas["SSEError"];
export type SSEMessageStart = Schemas["SSEMessageStart"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "eva.dev.token";

export const tokenStore = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token: string) => {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* private mode */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, await res.text());
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function devLogin(handle: string, displayName: string): Promise<User> {
  const out = await request<Schemas["TokenOut"]>("/auth/dev-login", {
    method: "POST",
    body: JSON.stringify({ handle, display_name: displayName }),
  });
  tokenStore.set(out.access_token);
  return out.user;
}

export const me = () => request<User>("/auth/me");
export const listConversations = () => request<Conversation[]>("/chat/conversations");
export const createConversation = () =>
  request<Conversation>("/chat/conversations", { method: "POST", body: "{}" });
export const listMessages = (conversationId: string) =>
  request<Message[]>(`/chat/conversations/${conversationId}/messages`);

export type ChatStreamEvent =
  | { type: "message_start"; data: SSEMessageStart }
  | { type: "delta"; text: string }
  | { type: "done"; data: SSEDone }
  | { type: "error"; data: SSEError };

export async function* sendMessage(
  conversationId: string,
  content: string,
  idempotencyKey: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const headers = new Headers({ "Content-Type": "application/json", Accept: "text/event-stream" });
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(`${API_URL}/chat/conversations/${conversationId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ content, idempotency_key: idempotencyKey }),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await res.text());

  for await (const ev of readSSE(res.body, signal)) {
    switch (ev.event) {
      case "message_start":
        yield { type: "message_start", data: JSON.parse(ev.data) as SSEMessageStart };
        break;
      case "delta":
        yield { type: "delta", text: (JSON.parse(ev.data) as Schemas["SSEDelta"]).text };
        break;
      case "done":
        yield { type: "done", data: JSON.parse(ev.data) as SSEDone };
        break;
      case "error":
        yield { type: "error", data: JSON.parse(ev.data) as SSEError };
        break;
    }
  }
}

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}
