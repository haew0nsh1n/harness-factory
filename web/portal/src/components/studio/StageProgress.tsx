const SDLC_STAGES = [
  { id: "discovery", label: "발견" },
  { id: "planning", label: "계획" },
  { id: "implementation", label: "구현" },
  { id: "testing", label: "테스트" },
  { id: "review", label: "검토" },
  { id: "release", label: "릴리스" },
  { id: "operations", label: "운영" },
] as const;

export interface StageProgressProps {
  stage: string;
}

export function StageProgress({ stage }: StageProgressProps) {
  const hasCurrentStage = SDLC_STAGES.some((item) => item.id === stage);

  return (
    <nav className="stage-progress" aria-label="SDLC 단계">
      <div className="stage-progress-header">
        <p className="eyebrow">SDLC 범위</p>
        {!hasCurrentStage ? (
          <p className="stage-unavailable">인터뷰 단계 미제공</p>
        ) : null}
      </div>
      <ol>
        {SDLC_STAGES.map((item) => (
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
