import type { tr } from "./tr";

/** Deep "any string" version of the Turkish messages so other locales must match its shape. */
type Widen<T> = T extends string
  ? string
  : T extends readonly string[]
    ? readonly string[]
    : { [K in keyof T]: Widen<T[K]> };

export type Messages = Widen<typeof tr>;
export type Locale = "tr" | "en";
