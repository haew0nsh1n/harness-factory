interface StatusBadgeProps {
  label: string;
}

const STATUS_LABELS: Record<string, string> = {
  active: "사용 중",
  approved: "승인됨",
  "build-queued": "빌드 대기",
  built: "빌드 완료",
  deprecated: "사용 중단 예정",
  draft: "초안",
  failed: "실패",
  "in-review": "검토 중",
  pilot: "파일럿",
  published: "게시됨",
  queued: "대기 중",
  rejected: "반려됨",
  revoked: "취소됨",
  running: "진행 중",
  stable: "안정",
  succeeded: "완료",
  unpublished: "미게시",
  validated: "검증됨",
};

function toClassName(label: string): string {
  return `status-badge status-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
}

export function StatusBadge({ label }: StatusBadgeProps) {
  return (
    <span className={toClassName(label)} data-status={label}>
      {STATUS_LABELS[label] ?? label}
    </span>
  );
}
