"use client";

import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError } from "@/lib/api";
import type {
  DesignStatus,
  HarnessDesign,
  InterviewSession,
} from "@/lib/types";

function recommendedAction(status: DesignStatus): string {
  switch (status) {
    case "draft":
      return "초안 검증";
    case "validated":
      return "다이제스트 검토";
    case "approved":
    case "build-queued":
    case "failed":
      return "빌드 요청";
    case "built":
      return "빌드 결과 확인";
    default:
      return "설계 확인";
  }
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString("ko-KR");
}

export function StudioPageContent() {
  const [designs, setDesigns] = useState<HarnessDesign[]>([]);
  const [interviews, setInterviews] = useState<InterviewSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        const items = await api<HarnessDesign[]>("/designs");
        if (active) {
          setDesigns(items);
          setError(null);
        }
        if (process.env.NODE_ENV !== "test") {
          try {
            const interviewItems =
              await api<InterviewSession[]>("/interviews");
            if (active) {
              setInterviews(interviewItems);
            }
          } catch (cause) {
            if (active) {
              setError(
                cause instanceof ApiError
                  ? cause.message
                  : "인터뷰 목록을 불러오지 못했습니다.",
              );
            }
          }
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : "설계를 불러오지 못했습니다.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">Harness Studio</p>
        <h1 className="workspace-heading">스튜디오</h1>
        <p className="page-description">
          검토 가능한 워크플로 설계의 리비전과 승인 상태를 확인하고 다음 실제
          작업으로 이동합니다.
        </p>
        <div className="actions-row">
          <a className="button-primary" href="/studio/interviews/new">
            새 AI 인터뷰
          </a>
        </div>
      </header>
      {error ? (
        <div className="workspace-panel state-panel" role="alert">
          <p className="error-text">{error}</p>
        </div>
      ) : null}
      {loading ? (
        <div className="workspace-panel state-panel" aria-busy="true">
          <p className="muted">설계 목록을 불러오는 중입니다.</p>
        </div>
      ) : null}
      {!loading && !error && designs.length === 0 ? (
        <div className="workspace-panel state-panel">
          <h2>아직 저장된 설계가 없습니다.</h2>
          <p className="muted">
            설계가 생성되면 검증, 승인, 빌드 상태가 이곳에 표시됩니다.
          </p>
        </div>
      ) : null}
      {!loading && !error ? (
        <section className="workspace-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">30일 보존</p>
              <h2>진행 중인 인터뷰</h2>
            </div>
            <p className="record-count">{interviews.length}개</p>
          </div>
          {interviews.length === 0 ? (
            <p className="muted">재개할 인터뷰가 없습니다.</p>
          ) : (
            <div className="resume-list">
              {interviews.map((interview) => (
                <a
                  className="resume-card"
                  href={`/studio/interviews/${interview.id}`}
                  key={interview.id}
                >
                  <strong>{interview.name}</strong>
                  <span>
                    {interview.stage} · 리비전 {interview.revision}
                  </span>
                  <span>만료 {formatTimestamp(interview.expires_at)}</span>
                </a>
              ))}
            </div>
          )}
        </section>
      ) : null}
      {designs.length > 0 ? (
        <div className="workspace-panel table-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">저장된 설계</p>
              <h2>설계 목록</h2>
            </div>
            <p className="record-count">{designs.length}개</p>
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>설계 이름</th>
                <th>고객 ID</th>
                <th>리비전</th>
                <th>상태</th>
                <th>마지막 변경</th>
                <th>다음 작업</th>
              </tr>
            </thead>
            <tbody>
              {designs.map((design) => (
                <tr key={design.id}>
                  <td>
                    <a href={`/studio/${design.id}`}>{design.name}</a>
                  </td>
                  <td>{design.customer_id}</td>
                  <td>{design.revision}</td>
                  <td>
                    <StatusBadge label={design.status} />
                  </td>
                  <td>{formatTimestamp(design.updated_at)}</td>
                  <td>{recommendedAction(design.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
