import { defaultLocale, type Locale } from "./config";
import { ko, type Messages } from "./messages/ko";
import { en } from "./messages/en";

// Register every locale's catalog here.
export const dictionaries: Record<Locale, Messages> = { ko, en };

export type TranslateParams = Record<string, string | number>;
export type TranslateFn = (key: string, params?: TranslateParams) => string;

export function getDictionary(locale: Locale): Messages {
  return dictionaries[locale] ?? dictionaries[defaultLocale];
}

// Resolves a dot-path key, falling back to the default locale then the raw key,
// and replaces {token} placeholders with the provided params.
export function translate(
  locale: Locale,
  key: string,
  params?: TranslateParams,
): string {
  const template =
    lookup(dictionaries[locale], key) ??
    lookup(dictionaries[defaultLocale], key) ??
    key;
  return interpolate(template, params);
}

function interpolate(template: string, params?: TranslateParams): string {
  if (!params) {
    return template;
  }
  return template.replace(/\{(\w+)\}/g, (match, token) =>
    token in params ? String(params[token]) : match,
  );
}

function lookup(dict: Messages | undefined, key: string): string | undefined {
  const value = key.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, dict);
  return typeof value === "string" ? value : undefined;
}
