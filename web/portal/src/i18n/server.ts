import { cookies } from "next/headers";

import { defaultLocale, isLocale, LOCALE_COOKIE, type Locale } from "./config";
import { translate, type TranslateFn } from "./dictionaries";

// Reads the locale from the cookie. Falls back to the default outside a request
// context (e.g. unit tests) so it never throws.
export async function getLocale(): Promise<Locale> {
  try {
    const store = await cookies();
    const value = store.get(LOCALE_COOKIE)?.value;
    return isLocale(value) ? value : defaultLocale;
  } catch {
    return defaultLocale;
  }
}

export async function getServerTranslations(): Promise<{
  locale: Locale;
  t: TranslateFn;
}> {
  const locale = await getLocale();
  return { locale, t: (key, params) => translate(locale, key, params) };
}
