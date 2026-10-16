/**
 * Backend'in gönderdiği WebAuthn (passkey ile giriş standardı) ayarlarını tarayıcının
 * `navigator.credentials` API'sine çevirir ve cevabı geri çevirir. Backend veriyi
 * JSON içinde base64url metni (URL'de sorun çıkarmayan base64 türü) olarak yollar,
 * tarayıcı ise ham bayt (ArrayBuffer) ister. Burada hiç şifreleme işi yapılmaz:
 * imzayı cihaz (telefon, parmak izi okuyucu vb.) atar, doğrulamayı backend yapar (ADR 0002).
 */

type Json = Record<string, unknown>;

export class PasskeyError extends Error {
  constructor(public reason: "unsupported" | "cancelled" | "failed") {
    super(reason);
  }
}

export function isPasskeySupported(): boolean {
  return (
    typeof window !== "undefined" && "PublicKeyCredential" in window && !!navigator.credentials
  );
}

function fromB64url(value: string): ArrayBuffer {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

function toB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

type Descriptor = { id: string; type: "public-key"; transports?: AuthenticatorTransport[] };

function descriptors(list: unknown): PublicKeyCredentialDescriptor[] | undefined {
  if (!Array.isArray(list)) return undefined;
  return (list as Descriptor[]).map((d) => ({ ...d, id: fromB64url(d.id) }));
}

async function run<T>(op: () => Promise<T | null>): Promise<T> {
  if (!isPasskeySupported()) throw new PasskeyError("unsupported");
  try {
    const result = await op();
    if (!result) throw new PasskeyError("cancelled");
    return result;
  } catch (err) {
    if (err instanceof PasskeyError) throw err;
    // NotAllowedError hem "kullanıcı vazgeçti" hem "süre doldu" demek; tarayıcı bilerek ayırmıyor.
    if (err instanceof DOMException && err.name === "NotAllowedError") {
      throw new PasskeyError("cancelled");
    }
    throw new PasskeyError("failed");
  }
}

/** Kayıt için `navigator.credentials.create` çağırır; backend'in doğrulayacağı JSON'u döner. */
export async function createPasskey(options: Json): Promise<Json> {
  const o = options as Json & {
    challenge: string;
    user: { id: string; name: string; displayName: string };
    excludeCredentials?: unknown;
  };
  const credential = await run(
    () =>
      navigator.credentials.create({
        publicKey: {
          ...(o as unknown as PublicKeyCredentialCreationOptions),
          challenge: fromB64url(o.challenge),
          user: { ...o.user, id: fromB64url(o.user.id) },
          excludeCredentials: descriptors(o.excludeCredentials),
        },
      }) as Promise<PublicKeyCredential | null>,
  );
  const response = credential.response as AuthenticatorAttestationResponse;
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      attestationObject: toB64url(response.attestationObject),
      transports: response.getTransports?.() ?? [],
    },
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}

/** Giriş için `navigator.credentials.get` çağırır; backend'in doğrulayacağı JSON'u döner. */
export async function getPasskey(options: Json): Promise<Json> {
  const o = options as Json & { challenge: string; allowCredentials?: unknown };
  const credential = await run(
    () =>
      navigator.credentials.get({
        publicKey: {
          ...(o as unknown as PublicKeyCredentialRequestOptions),
          challenge: fromB64url(o.challenge),
          allowCredentials: descriptors(o.allowCredentials),
        },
      }) as Promise<PublicKeyCredential | null>,
  );
  const response = credential.response as AuthenticatorAssertionResponse;
  return {
    id: credential.id,
    rawId: toB64url(credential.rawId),
    type: credential.type,
    response: {
      clientDataJSON: toB64url(response.clientDataJSON),
      authenticatorData: toB64url(response.authenticatorData),
      signature: toB64url(response.signature),
      userHandle: response.userHandle ? toB64url(response.userHandle) : null,
    },
    authenticatorAttachment: credential.authenticatorAttachment,
    clientExtensionResults: credential.getClientExtensionResults(),
  };
}
