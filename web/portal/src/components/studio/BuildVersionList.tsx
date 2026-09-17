"use client";

import { StatusBadge } from "@/components/StatusBadge";
import { useLocale, useTranslations } from "@/i18n/I18nProvider";
import type { BuildJob } from "@/lib/types";

function formatWhen(value: string | null, locale: string): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleString(locale);
}

export function BuildVersionList({ builds }: { builds: BuildJob[] }) {
  const t = useTranslations();
  const locale = useLocale();
  const recent = builds.slice(0, 3);
  if (recent.length === 0) {
    return null;
  }
  return (
    <section className="workspace-panel">
      <p className="eyebrow">{t("studioDesign.versionsEyebrow")}</p>
      <h2>{t("studioDesign.versionsHeading")}</h2>
      <ul className="version-list">
        {recent.map((build) => (
          <li key={build.id} className="version-row">
            <StatusBadge label={build.status} />
            <code className="digest-text">{build.design_digest.slice(0, 12)}</code>
            <span className="muted">
              {formatWhen(build.finished_at ?? build.created_at, locale)}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
