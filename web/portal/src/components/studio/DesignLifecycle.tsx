"use client";

import { useTranslations } from "@/i18n/I18nProvider";
import type { DesignStatus } from "@/lib/types";

// Index of the stage the user acts on next (0 초안, 1 검증, 2 검토, 3 빌드).
const CURRENT_INDEX: Record<DesignStatus, number> = {
  draft: 1,
  validated: 2,
  approved: 3,
  "build-queued": 3,
  built: 4,
  failed: 3,
};

type Phase = "done" | "current" | "upcoming" | "failed";

function phaseAt(index: number, current: number, failed: boolean): Phase {
  if (index < current) {
    return "done";
  }
  if (index === current) {
    return failed ? "failed" : "current";
  }
  return "upcoming";
}

interface DesignLifecycleProps {
  status: DesignStatus;
  saving: boolean;
  onSaveDraft: () => void;
  onValidate: () => void;
  onApprove: () => void;
  onReject: () => void;
  onBuild: () => void;
}

export function DesignLifecycle({
  status,
  saving,
  onSaveDraft,
  onValidate,
  onApprove,
  onReject,
  onBuild,
}: DesignLifecycleProps): React.JSX.Element {
  const t = useTranslations();
  const current = CURRENT_INDEX[status] ?? 1;
  const failed = status === "failed";

  const box = (
    label: string,
    onClick: () => void,
    disabled: boolean,
    phase: Phase,
    extra = "",
  ) => (
    <button
      type="button"
      className={`lifecycle-box lifecycle-${phase}${extra ? ` ${extra}` : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {label}
    </button>
  );

  const approvePhase: Phase =
    current > 2 ? "done" : current === 2 ? "current" : "upcoming";
  const rejectPhase: Phase = current === 2 ? "current" : "upcoming";

  return (
    <nav className="lifecycle" aria-label={t("lifecycle.aria")}>
      {box(
        t("studioDesign.saveDraftBtn"),
        onSaveDraft,
        saving,
        phaseAt(0, current, failed),
      )}
      <span className="lifecycle-arrow" aria-hidden="true" />
      {box(
        t("studioDesign.validateBtn"),
        onValidate,
        saving || status !== "draft",
        phaseAt(1, current, failed),
      )}
      <span className="lifecycle-arrow lifecycle-arrow-fork" aria-hidden="true" />
      <div className="lifecycle-fork">
        {box(
          t("studioDesign.approveDigestBtn"),
          onApprove,
          saving || status !== "validated",
          approvePhase,
          "lifecycle-fork-item",
        )}
        {box(
          t("studioDesign.rejectReviewBtn"),
          onReject,
          saving || status !== "validated",
          rejectPhase,
          "lifecycle-fork-item",
        )}
      </div>
      <span className="lifecycle-arrow" aria-hidden="true" />
      {box(
        t("studioDesign.requestBuildBtn"),
        onBuild,
        saving || !["approved", "failed"].includes(status),
        phaseAt(3, current, failed),
      )}
    </nav>
  );
}
