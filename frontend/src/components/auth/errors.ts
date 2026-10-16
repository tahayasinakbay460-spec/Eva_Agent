import { messages } from "@/i18n";
import { ApiError } from "@/lib/api/client";
import { PasskeyError } from "@/lib/webauthn";

const t = messages();

/** Hatanın nerede olduğu, genel bir 400 hatasının kullanıcıya hangi mesajla gösterileceğini belirler. */
export type ErrorContext = "passkey" | "credentials" | "code" | "form";

export function errorText(err: unknown, context: ErrorContext): string {
  const e = t.auth.errors;
  if (err instanceof PasskeyError) return e[err.reason];
  if (!(err instanceof ApiError)) return e.network;
  if (err.status === 429) return e.tooMany;
  if (err.status === 422) {
    return err.message.includes("Weak password") ? e.weakPassword : e.invalidEmail;
  }
  if (err.status === 400) {
    if (context === "credentials") return e.wrongCredentials;
    if (context === "code") return e.wrongCode;
  }
  return e.failed;
}
