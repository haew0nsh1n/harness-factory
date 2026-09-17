"use client";

import { SDLC_STAGES } from "@/components/studio/StageProgress";
import { useTranslations } from "@/i18n/I18nProvider";

// Shows the full SDLC scope and marks the stages selected/relevant for this record.
export function SdlcScope({ selected }: { selected: readonly string[] }) {
  const t = useTranslations();
  const selectedSet = new Set(selected);
  return (
    <ul className="sdlc-scope" aria-label={t("sdlcScope.aria")}>
      {SDLC_STAGES.map((item) => {
        const isSelected = selectedSet.has(item.id);
        return (
          <li
            key={item.id}
            className="sdlc-scope-stage"
            data-selected={isSelected ? "true" : "false"}
            aria-label={`${t(item.labelKey)} · ${t(
              isSelected ? "sdlcScope.included" : "sdlcScope.excluded",
            )}`}
          >
            <span aria-hidden="true">{t(item.labelKey)}</span>
          </li>
        );
      })}
    </ul>
  );
}
