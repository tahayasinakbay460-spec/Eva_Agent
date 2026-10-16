/**
 * EVA API'sini çağırmak için ince, tipli bir sarmalayıcı. Tipler `schema.d.ts`'ten gelir;
 * o dosya backend'in OpenAPI şemasından otomatik üretilir (`npm run gen-client`) - elle
 * asla düzenlenmez.
 *
 * Giriş passkey ile ya da e-posta + şifre + e-postaya gelen kodla yapılır (ADR 0002).
 * Şimdilik oturum token'ı localStorage'da duruyor; bir sonraki adım onu JavaScript'in
 * okuyamadığı httpOnly bir çereze taşımak ve yenileme token'ını döndürmek (§11.2).
 */

import { readSSE } from "../sse";
import { createPasskey, getPasskey } from "../webauthn";
import type { components } from "./schema";

type Schemas = components["schemas"];
export type User = Schemas["UserOut"];
export type Conversation = Schemas["ConversationOut"];
export type Message = Schemas["MessageOut"];
export type SSEDone = Schemas["SSEDone"];
export type SSEError = Schemas["SSEError"];
export type SSEMessageStart = Schemas["SSEMessageStart"];

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "eva.token";

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
      /* gizli sekmede localStorage hata verebilir; görmezden gel */
    }
  },
  clear: () => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* hata olursa görmezden gel */
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

export type SignUpForm = Schemas["PasskeySignUpRequest"];
type PasskeyOptions = Schemas["PasskeyOptionsOut"];

async function finishPasskey(
  path: string,
  flow: PasskeyOptions,
  credential: Record<string, unknown>,
): Promise<User> {
  const body: Schemas["PasskeyVerifyRequest"] = { flow_id: flow.flow_id, credential };
  const out = await request<Schemas["TokenOut"]>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
  tokenStore.set(out.access_token);
  return out.user;
}

/** Hesap açar: cihaz bir passkey oluşturur, backend onu doğrular. */
export async function passkeySignUp(form: SignUpForm): Promise<User> {
  const flow = await request<PasskeyOptions>("/auth/passkey/register/options", {
    method: "POST",
    body: JSON.stringify(form),
  });
  const credential = await createPasskey(flow.options);
  return finishPasskey("/auth/passkey/register/verify", flow, credential);
}

/** Bu cihazda kayıtlı herhangi bir passkey ile giriş yapar (kullanıcı adı gerekmez). */
export async function passkeyLogin(): Promise<User> {
  const flow = await request<PasskeyOptions>("/auth/passkey/login/options", { method: "POST" });
  const credential = await getPasskey(flow.options);
  return finishPasskey("/auth/passkey/login/verify", flow, credential);
}

/*
 * E-posta + şifre: kod gönderen her adım bir "akış" (flow) döner; e-postaya gelen kod
 * girilince o akış tamamlanır.
 */

export type PasswordSignUpForm = Schemas["PasswordSignUpRequest"];
export type CodeFlow = Schemas["CodeFlowOut"];

const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

async function finishWithCode(path: string, flowId: string, code: string): Promise<User> {
  const out = await post<Schemas["TokenOut"]>(path, { flow_id: flowId, code });
  tokenStore.set(out.access_token);
  return out.user;
}

export const passwordSignUpStart = (form: PasswordSignUpForm) =>
  post<CodeFlow>("/auth/password/register", form);
export const passwordSignUpFinish = (flowId: string, code: string) =>
  finishWithCode("/auth/password/register/verify", flowId, code);

export const passwordLoginStart = (email: string, password: string) =>
  post<CodeFlow>("/auth/password/login", { email, password });
export const passwordLoginFinish = (flowId: string, code: string) =>
  finishWithCode("/auth/password/login/verify", flowId, code);

export const passwordResetStart = (email: string, locale: PasswordSignUpForm["locale"]) =>
  post<CodeFlow>("/auth/password/reset", { email, locale });
export const passwordResetFinish = (flowId: string, code: string, newPassword: string) =>
  post<void>("/auth/password/reset/verify", {
    flow_id: flowId,
    code,
    new_password: newPassword,
  });

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

/* Anılar ("EVA ne biliyor?" ekranı). */

export type Memory = Schemas["MemoryOut"];
export type MemoryCreate = Schemas["MemoryCreate"];
export type MemoryUpdate = Schemas["MemoryUpdate"];
export type MemoryKind = Memory["kind"];

export const listMemories = (kind?: MemoryKind) =>
  request<Memory[]>(`/memories${kind ? `?kind=${kind}` : ""}`);
export const addMemory = (body: MemoryCreate) => post<Memory>("/memories", body);
export const updateMemory = (id: string, body: MemoryUpdate) =>
  request<Memory>(`/memories/${id}`, { method: "PATCH", body: JSON.stringify(body) });
export const forgetMemory = (id: string) => request<void>(`/memories/${id}`, { method: "DELETE" });

/* Sesli / görüntülü görüşme (Faz 2). Ses bu API'den geçmez: tarayıcı LiveKit odasına bağlanır. */

export type Call = Schemas["CallOut"];
export type CallMode = Call["mode"];
export type LatencyReport = Schemas["LatencyReportOut"];

export const startCall = (mode: CallMode = "voice") => post<Call>("/voice/calls", { mode });
export const endCall = (callId: string) => post<void>(`/voice/calls/${callId}/end`, {});
export const latencyReport = () => request<LatencyReport>("/voice/latency");
