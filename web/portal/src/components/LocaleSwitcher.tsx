"use client";

import { locales, localeNames, type Locale } from "@/i18n/config";
import { useI18n } from "@/i18n/I18nProvider";

export function LocaleSwitcher() {
  const { locale, t, setLocale } = useI18n();

  return (
    <div className="locale-switcher">
      <label className="locale-switcher-label" htmlFor="hf-locale-select">
        {t("locale.label")}
      </label>
      <select
        id="hf-locale-select"
        className="locale-switcher-select"
        value={locale}
        onChange={(event) => setLocale(event.target.value as Locale)}
      >
        {locales.map((code) => (
          <option key={code} value={code}>
            {localeNames[code]}
          </option>
        ))}
      </select>
    </div>
  );
}
