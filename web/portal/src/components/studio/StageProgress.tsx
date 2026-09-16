import { createContext, useContext, type ReactNode } from "react";

export const SDLC_STAGES = [
  { id: "discovery", label: "발견" },
  { id: "planning", label: "계획" },
  { id: "implementation", label: "구현" },
  { id: "testing", label: "테스트" },
  { id: "review", label: "검토" },
  { id: "release", label: "릴리스" },
  { id: "operations", label: "운영" },
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
  const contextualStages = useContext(selectedStagesContext);
  const selected = selectedStages ?? contextualStages ?? SDLC_STAGES.map((item) => item.id);
  const visibleStages = SDLC_STAGES.filter((item) => selected.includes(item.id));
  const hasCurrentStage = visibleStages.some((item) => item.id === stage);
  const isSummary = stage === "summary";

  return (
    <nav className="stage-progress" aria-label="SDLC 단계">
      <div className="stage-progress-header">
        <p className="eyebrow">SDLC 범위</p>
        {!hasCurrentStage ? (
          <p className="stage-unavailable">
            {isSummary ? "선택한 단계 완료" : "인터뷰 단계 미제공"}
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
              {item.label}
            </span>
          </li>
        ))}
      </ol>
    </nav>
  );
}
