"use client";

import { useTranslations } from "@/i18n/I18nProvider";

interface OperationStatusProps {
  kind: string | null;
  recovering?: boolean;
}

export function OperationStatus({ kind, recovering = false }: OperationStatusProps) {
  const t = useTranslations();
  if (!kind) {
    return null;
  }
  const labelKey = `operationStatus.labels.${kind}`;
  const translatedLabel = t(labelKey);
  const labelText =
    translatedLabel === labelKey ? t("operationStatus.fallback") : translatedLabel;
  return (
    <p className="operation-status" role="status" aria-live="polite">
      <span className="operation-dots" aria-hidden="true">•••</span>
      {recovering ? t("operationStatus.recoveringPrefix") : ""}
      {labelText}{t("operationStatus.suffix")}
    </p>
  );
}
