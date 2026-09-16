interface OperationStatusProps {
  kind: string | null;
  recovering?: boolean;
}

const labels: Record<string, string> = {
  start: "첫 질문을 준비하고 있습니다",
  answer: "답변을 처리하고 다음 질문을 준비하고 있습니다",
  proposal: "설계 제안을 생성하고 있습니다",
  confirmation: "근거 결정을 저장하고 있습니다",
  apply: "정확한 제안을 설계에 적용하고 있습니다",
  delete: "인터뷰를 삭제하고 있습니다",
};

export function OperationStatus({ kind, recovering = false }: OperationStatusProps) {
  if (!kind) {
    return null;
  }
  return (
    <p className="operation-status" role="status" aria-live="polite">
      <span className="operation-dots" aria-hidden="true">•••</span>
      {recovering ? "저장된 작업 상태를 확인하고 있습니다. " : ""}
      {labels[kind] ?? "인터뷰 작업을 처리하고 있습니다"} 완료될 때까지 입력과 변경 작업을 잠시 기다려 주세요.
    </p>
  );
}
