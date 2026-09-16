"use client";

import type { EvidenceItem } from "@/components/studio/InterviewWorkspace";
import { useTranslations } from "@/i18n/I18nProvider";

export interface EvidenceRailProps {
  items: EvidenceItem[];
  onConfirm?: (id: string) => void;
  kinds?: EvidenceItem["kind"][];
}

const GROUPS: Array<{
  kind: EvidenceItem["kind"];
  labelKey: string;
  emptyKey: string;
}> = [
  {
    kind: "confirmed",
    labelKey: "evidence.confirmedLabel",
    emptyKey: "evidence.confirmedEmpty",
  },
  {
    kind: "assumption",
    labelKey: "evidence.assumptionLabel",
    emptyKey: "evidence.assumptionEmpty",
  },
  {
    kind: "unknown",
    labelKey: "evidence.unknownLabel",
    emptyKey: "evidence.unknownEmpty",
  },
  {
    kind: "proposed",
    labelKey: "evidence.proposedLabel",
    emptyKey: "evidence.proposedEmpty",
  },
];

export function EvidenceRail({
  items,
  onConfirm,
  kinds,
}: EvidenceRailProps) {
  const t = useTranslations();
  const visibleGroups = kinds
    ? GROUPS.filter((group) => kinds.includes(group.kind))
    : GROUPS;

  if (items.length === 0) {
    return (
      <div className="evidence-empty">
        <p className="muted">{t("evidence.noEvidence")}</p>
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
              <h3 id={`evidence-${group.kind}-heading`}>{t(group.labelKey)}</h3>
              <span aria-label={t("evidence.countAria", { label: t(group.labelKey), count: groupItems.length })}>
                {groupItems.length}
              </span>
            </div>
            {groupItems.length === 0 ? (
              <p className="evidence-group-empty">{t(group.emptyKey)}</p>
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
                              {t("evidence.sourceIndexed", { index: index + 1, turnId })}
                            </a>
                          ))}
                        </span>
                      ) : item.sourceTurnId ? (
                        <a href={`#turn-${item.sourceTurnId}`}>
                          {t("evidence.source", { turnId: item.sourceTurnId })}
                        </a>
                      ) : (
                        <span>{t("evidence.savedProfile")}</span>
                      )}
                      {item.kind === "proposed" && onConfirm ? (
                        <button
                          className="button-secondary button-compact"
                          type="button"
                          onClick={() => onConfirm(item.id)}
                        >
                          {t("evidence.confirmFact")}
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
