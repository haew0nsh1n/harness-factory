import type { EvidenceItem } from "@/components/studio/InterviewWorkspace";

export interface EvidenceRailProps {
  items: EvidenceItem[];
  onConfirm?: (id: string) => void;
  kinds?: EvidenceItem["kind"][];
}

const GROUPS: Array<{
  kind: EvidenceItem["kind"];
  label: string;
  emptyLabel: string;
}> = [
  {
    kind: "confirmed",
    label: "확인된 사실",
    emptyLabel: "확인된 사실이 없습니다.",
  },
  {
    kind: "assumption",
    label: "가정",
    emptyLabel: "기록된 가정이 없습니다.",
  },
  {
    kind: "unknown",
    label: "미확인",
    emptyLabel: "미확인 항목이 없습니다.",
  },
  {
    kind: "proposed",
    label: "검토할 제안",
    emptyLabel: "검토할 제안이 없습니다.",
  },
];

export function EvidenceRail({
  items,
  onConfirm,
  kinds,
}: EvidenceRailProps) {
  const visibleGroups = kinds
    ? GROUPS.filter((group) => kinds.includes(group.kind))
    : GROUPS;

  if (items.length === 0) {
    return (
      <div className="evidence-empty">
        <p className="muted">저장된 근거가 없습니다.</p>
      </div>
    );
  }

  return (
    <div className="evidence-rail">
      {visibleGroups.map((group) => {
        const groupItems = items.filter((item) => item.kind === group.kind);

        return (
          <section
            className={`evidence-group evidence-${group.kind}`}
            key={group.kind}
            aria-labelledby={`evidence-${group.kind}-heading`}
          >
            <div className="evidence-group-heading">
              <h3 id={`evidence-${group.kind}-heading`}>{group.label}</h3>
              <span aria-label={`${group.label} ${groupItems.length}개`}>
                {groupItems.length}
              </span>
            </div>
            {groupItems.length === 0 ? (
              <p className="evidence-group-empty">{group.emptyLabel}</p>
            ) : (
              <ul>
                {groupItems.map((item) => (
                  <li key={item.id}>
                    <p>{item.statement}</p>
                    <div className="evidence-actions">
                      {item.sourceTurnIds?.length ? (
                        <span className="source-links">
                          {item.sourceTurnIds.map((turnId, index) => (
                            <a href={`#turn-${turnId}`} key={turnId}>
                              출처 {index + 1}: {turnId}
                            </a>
                          ))}
                        </span>
                      ) : item.sourceTurnId ? (
                        <a href={`#turn-${item.sourceTurnId}`}>
                          출처: {item.sourceTurnId}
                        </a>
                      ) : (
                        <span>저장된 프로필</span>
                      )}
                      {item.kind === "proposed" && onConfirm ? (
                        <button
                          className="button-secondary button-compact"
                          type="button"
                          onClick={() => onConfirm(item.id)}
                        >
                          사실 확인
                        </button>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
