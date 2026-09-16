"use client";

import { useTranslations } from "@/i18n/I18nProvider";

interface StatusBadgeProps {
  label: string;
}

function toClassName(label: string): string {
  return `status-badge status-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function StatusBadge({ label }: StatusBadgeProps) {
  const t = useTranslations();
  const key = `status.${label}`;
  const translated = t(key);

  return (
    <span className={toClassName(label)} data-status={label}>
      {translated === key ? label : translated}
    </span>
  );
}
