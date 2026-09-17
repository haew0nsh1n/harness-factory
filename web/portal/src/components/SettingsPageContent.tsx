"use client";

import { useTranslations } from "@/i18n/I18nProvider";

export function SettingsPageContent(): React.JSX.Element {
  const t = useTranslations();

  return (
    <div className="page-stack">
      <section className="workspace-panel">
        <p className="eyebrow">{t("settings.eyebrow")}</p>
        <h1 className="workspace-heading">{t("settings.heading")}</h1>
        <p className="page-description">{t("settings.intro")}</p>
        <p className="muted">{t("settings.comingSoon")}</p>
      </section>
    </div>
  );
}
