import type { tr } from "./tr";

/**
 * Türkçe metinlerin, içindeki her metni "herhangi bir string" yapan kopyası (iç içe her
 * seviyede). Böylece diğer diller (ör. en) aynı anahtarlara sahip olmak zorunda kalır.
 */
type Widen<T> = T extends string
  ? string
  : T extends readonly string[]
    ? readonly string[]
    : { [K in keyof T]: Widen<T[K]> };

export type Messages = Widen<typeof tr>;
export type Locale = "tr" | "en";
