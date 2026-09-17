"use client";

import { createContext, useContext, type ReactNode } from "react";

import { useTranslations } from "@/i18n/I18nProvider";

export const SDLC_STAGES = [
  { id: "discovery", labelKey: "stages.discovery" },
  { id: "planning", labelKey: "stages.planning" },
  { id: "implementation", labelKey: "stages.implementation" },
  { id: "testing", labelKey: "stages.testing" },
  { id: "review", labelKey: "stages.review" },
  { id: "release", labelKey: "stages.release" },
  { id: "operations", labelKey: "stages.operations" },
] as const;

const selectedStagesContext = createContext<readonly string[] | null>(null);

export function SelectedStagesProvider({
  stages,
  children,
}: {
  stages?: readonly string[];
  children: ReactNode;
}) {
  return (
    <selectedStagesContext.Provider value={stages ?? null}>
      {children}
    </selectedStagesContext.Provider>
  );
}

export interface StageProgressProps {
  stage: string;
  selectedStages?: readonly string[];
  // When set, show every SDLC stage and mark these as in-scope (green).
  highlight?: readonly string[];
}

export function StageProgress({ stage, selectedStages, highlight }: StageProgressProps) {
  const t = useTranslations();
  const contextualStages = useContext(selectedStagesContext);
  const overview = highlight !== undefined;
  const selected = overview
    ? SDLC_STAGES.map((item) => item.id)
    : selectedStages ?? contextualStages ?? SDLC_STAGES.map((item) => item.id);
  const visibleStages = SDLC_STAGES.filter((item) => selected.includes(item.id));
  const inScope = new Set(highlight ?? []);
  const hasCurrentStage = visibleStages.some((item) => item.id === stage);
  const isSummary = stage === "summary";

  return (
    <nav className="stage-progress" aria-label={t("stageProgress.aria")}>
      <div className="stage-progress-header">
        <p className="eyebrow">{t("stageProgress.scope")}</p>
        {!overview && !hasCurrentStage ? (
          <p className="stage-unavailable">
            {isSummary ? t("stageProgress.selectedComplete") : t("stageProgress.interviewUnavailable")}
          </p>
        ) : null}
      </div>
      <ol>
        {visibleStages.map((item) => {
          const isCurrent = item.id === stage;
          const className =
            [isCurrent ? "stage-current" : null, overview && inScope.has(item.id) ? "stage-in-scope" : null]
              .filter(Boolean)
              .join(" ") || undefined;
          return (
            <li key={item.id} className={className}>
              <span aria-current={isCurrent ? "step" : undefined}>
                {t(item.labelKey)}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
