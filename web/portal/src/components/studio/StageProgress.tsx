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
}

export function StageProgress({ stage, selectedStages }: StageProgressProps) {
  const t = useTranslations();
  const contextualStages = useContext(selectedStagesContext);
  const selected = selectedStages ?? contextualStages ?? SDLC_STAGES.map((item) => item.id);
  const visibleStages = SDLC_STAGES.filter((item) => selected.includes(item.id));
  const hasCurrentStage = visibleStages.some((item) => item.id === stage);
  const isSummary = stage === "summary";

  return (
    <nav className="stage-progress" aria-label={t("stageProgress.aria")}>
      <div className="stage-progress-header">
        <p className="eyebrow">{t("stageProgress.scope")}</p>
        {!hasCurrentStage ? (
          <p className="stage-unavailable">
            {isSummary ? t("stageProgress.selectedComplete") : t("stageProgress.interviewUnavailable")}
          </p>
        ) : null}
      </div>
      <ol>
        {visibleStages.map((item) => (
          <li
            key={item.id}
            className={item.id === stage ? "stage-current" : undefined}
          >
            <span aria-current={item.id === stage ? "step" : undefined}>
              {t(item.labelKey)}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
