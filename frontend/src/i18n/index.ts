import { en } from "./en";
import { tr } from "./tr";
import type { Locale, Messages } from "./types";

const catalog: Record<Locale, Messages> = { tr, en };

export const DEFAULT_LOCALE: Locale = "tr";

export function messages(locale: Locale = DEFAULT_LOCALE): Messages {
  return catalog[locale];
}

export type { Locale, Messages };
