import type { Locale } from "./config";

// Best-effort human-readable labels for known validation scenario IDs. IDs stay
// as immutable lowercase-hyphen identifiers; these labels are display-only.
const SCENARIO_LABELS: Record<string, Partial<Record<Locale, string>>> = {
  "normal-handoff": { ko: "정상 인계", en: "Normal handoff" },
  "approval-denied": { ko: "승인 거부", en: "Approval denied" },
  "missing-report": { ko: "보고서 누락", en: "Missing report" },
  "review-failed": { ko: "리뷰 실패", en: "Review failed" },
  "resume-with-url": { ko: "URL 확인 후 재개", en: "Resume with URL" },
  "uncertain-creation": { ko: "생성 불확실", en: "Uncertain creation" },
  "report-injection": { ko: "보고서 인젝션", en: "Report injection" },
};

export function scenarioLabel(id: string, locale: Locale): string {
  return SCENARIO_LABELS[id]?.[locale] ?? "";
}
