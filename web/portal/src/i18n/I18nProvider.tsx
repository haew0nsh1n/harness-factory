"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";
import { useRouter } from "next/navigation";

import { defaultLocale, LOCALE_COOKIE, type Locale } from "./config";
import { translate, type TranslateFn } from "./dictionaries";
interface I18nContextValue {
  locale: Locale;
  t: TranslateFn;
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// Stable fallback for use outside the provider (e.g. isolated unit tests), so
// consumers that depend on `t` identity don't re-run every render.
const fallbackValue: I18nContextValue = {
  locale: defaultLocale,
  t: (key, params) => translate(defaultLocale, key, params),
  setLocale: () => {},
};

// Receives the locale from the server layout and re-renders on router refresh,
// so a language change flows through both server and client components.
export function I18nProvider({
  locale,
  children,
}: {
  locale: Locale;
  children: ReactNode;
}) {
  const router = useRouter();

  const setLocale = useCallback(
    (next: Locale) => {
      document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
      router.refresh();
    },
    [router],
  );

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      t: (key, params) => translate(locale, key, params),
      setLocale,
    }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

// Falls back to the default locale when used outside the provider (e.g. tests).
export function useI18n(): I18nContextValue {
  return useContext(I18nContext) ?? fallbackValue;
}

export function useTranslations(): TranslateFn {
  return useI18n().t;
}

export function useLocale(): Locale {
  return useI18n().locale;
}
