// Central locale configuration.
//
// To add a new language:
//   1. Add its code to `locales` below.
//   2. Add a display name to `localeNames`.
//   3. Create `messages/<code>.ts` mirroring `messages/ko.ts`.
//   4. Register it in `dictionaries.ts`.
export const locales = ["ko", "en"] as const;

export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "ko";

// Native display names shown in the language switcher.
export const localeNames: Record<Locale, string> = {
  ko: "한국어",
  en: "English",
};

export const LOCALE_COOKIE = "hf_locale";

export function isLocale(value: string | undefined | null): value is Locale {
  return Boolean(value) && (locales as readonly string[]).includes(value as string);
}
