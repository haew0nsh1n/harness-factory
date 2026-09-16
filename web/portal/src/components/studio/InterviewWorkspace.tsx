"use client";

import type React from "react";
import { useId, useRef, useState } from "react";

import { EvidenceRail } from "@/components/studio/EvidenceRail";
import { StageProgress } from "@/components/studio/StageProgress";
import { useTranslations } from "@/i18n/I18nProvider";

export interface EvidenceItem {
  id: string;
  statement: string;
  sourceTurnIds?: string[];
  sourceTurnId?: string;
  kind: "confirmed" | "assumption" | "unknown" | "proposed";
}

export interface InterviewWorkspaceProps {
  title: string;
  stage: string;
  evidence: EvidenceItem[];
  conversation: React.ReactNode;
  composer: React.ReactNode;
  onConfirm?: (id: string) => void;
  boundary?: string;
}

type MobileRailTab = "evidence" | "proposal";

export function InterviewWorkspace({
  title,
  stage,
  evidence,
  conversation,
  composer,
  onConfirm,
  boundary,
}: InterviewWorkspaceProps) {
  const t = useTranslations();
  const displayBoundary = boundary ?? t("interviewWorkspace.boundary");
  const [activeTab, setActiveTab] = useState<MobileRailTab>("evidence");
  const tabListId = useId();
  const evidencePanelId = `${tabListId}-evidence-panel`;
  const proposalPanelId = `${tabListId}-proposal-panel`;
  const evidenceTabRef = useRef<HTMLButtonElement>(null);
  const proposalTabRef = useRef<HTMLButtonElement>(null);

  function selectTab(tab: MobileRailTab): void {
    setActiveTab(tab);
    if (tab === "evidence") {
      evidenceTabRef.current?.focus();
    } else {
      proposalTabRef.current?.focus();
    }
  }

  function handleTabKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
  ): void {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      selectTab(activeTab === "evidence" ? "proposal" : "evidence");
    }
  }

  return (
    <section className="interview-workspace" aria-labelledby={`${tabListId}-title`}>
      <header className="interview-workspace-header">
        <div>
          <p className="eyebrow">{t("interviewWorkspace.eyebrow")}</p>
          <h2 id={`${tabListId}-title`}>{title}</h2>
        </div>
        <p className="workspace-boundary">{displayBoundary}</p>
      </header>

      <div className="interview-workspace-grid">
        <StageProgress stage={stage} />

        <div className="conversation-column">
          <div className="conversation-surface">{conversation}</div>
        </div>

        <aside className="evidence-column" aria-label={t("interviewWorkspace.evidenceAria")}>
          <EvidenceRail items={evidence} onConfirm={onConfirm} />
        </aside>

        <div className="mobile-evidence-column">
          <div className="workspace-tabs" role="tablist" aria-label={t("interviewWorkspace.evidenceTabsAria")}>
            <button
              ref={evidenceTabRef}
              id={`${tabListId}-evidence-tab`}
              type="button"
              role="tab"
              aria-selected={activeTab === "evidence"}
              aria-controls={evidencePanelId}
              tabIndex={activeTab === "evidence" ? 0 : -1}
              onClick={() => selectTab("evidence")}
              onKeyDown={handleTabKeyDown}
            >
              {t("interviewWorkspace.evidenceTab")}
            </button>
            <button
              ref={proposalTabRef}
              id={`${tabListId}-proposal-tab`}
              type="button"
              role="tab"
              aria-selected={activeTab === "proposal"}
              aria-controls={proposalPanelId}
              tabIndex={activeTab === "proposal" ? 0 : -1}
              onClick={() => selectTab("proposal")}
              onKeyDown={handleTabKeyDown}
            >
              {t("interviewWorkspace.proposalTab")}
            </button>
          </div>
          <div
            id={evidencePanelId}
            role="tabpanel"
            aria-labelledby={`${tabListId}-evidence-tab`}
            hidden={activeTab !== "evidence"}
          >
            <EvidenceRail
              items={evidence}
              kinds={["confirmed", "assumption", "unknown"]}
              onConfirm={onConfirm}
            />
          </div>
          <div
            id={proposalPanelId}
            role="tabpanel"
            aria-labelledby={`${tabListId}-proposal-tab`}
            hidden={activeTab !== "proposal"}
          >
            <EvidenceRail
              items={evidence}
              kinds={["proposed"]}
              onConfirm={onConfirm}
            />
          </div>
        </div>

        <div className="composer-surface">{composer}</div>
      </div>
    </section>
  );
}
