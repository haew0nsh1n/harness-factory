"use client";

import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { HarnessDesign, RegistryAssetSummary } from "@/lib/types";

interface DashboardMetrics {
  totalDesigns: number;
  validated: number;
  approved: number;
  built: number;
  published: number;
}

function summarizeMetrics(
  designs: HarnessDesign[],
  assets: RegistryAssetSummary[],
): DashboardMetrics {
  return {
    totalDesigns: designs.length,
    validated: designs.filter((design) => design.status === "validated").length,
    approved: designs.filter((design) => design.status === "approved").length,
    built: designs.filter((design) => design.status === "built").length,
    published: assets.reduce(
      (count, asset) =>
        count +
        asset.versions.filter((version) => version.status === "published").length,
      0,
    ),
  };
}

export function DashboardPageContent() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        const [designs, assets] = await Promise.all([
          api<HarnessDesign[]>("/designs"),
          api<RegistryAssetSummary[]>("/registry/assets?type=workflow"),
        ]);
        if (active) {
          setMetrics(summarizeMetrics(designs, assets));
        }
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof ApiError
              ? cause.message
              : "대시보드 데이터를 불러오지 못했습니다.",
          );
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <section className="workspace-panel state-panel" role="alert">
        <p className="eyebrow">불러오기 실패</p>
        <h1 className="workspace-heading">작업 현황을 표시할 수 없습니다.</h1>
        <p className="error-text">{error}</p>
      </section>
    );
  }

  if (!metrics) {
    return (
      <section className="workspace-panel state-panel" aria-busy="true">
        <p className="eyebrow">대시보드</p>
        <h1 className="workspace-heading">작업 현황을 불러오는 중입니다.</h1>
      </section>
    );
  }

  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">운영 대시보드</p>
        <h1 className="workspace-heading">검토가 필요한 작업을 확인하세요.</h1>
        <p className="page-description">
          설계가 검증, 승인, 빌드, 게시 단계 중 어디에 있는지 실제 데이터로
          요약합니다.
        </p>
      </header>
      <div className="status-overview">
        <section className="workspace-panel metric-panel">
          <h2>전체 설계</h2>
          <span className="metric-value">{metrics.totalDesigns}</span>
          <a href="/studio">설계 목록 보기</a>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>검증됨</h2>
          <span className="metric-value">{metrics.validated}</span>
          <p>다이제스트 검토 대기</p>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>승인됨</h2>
          <span className="metric-value">{metrics.approved}</span>
          <p>빌드 요청 가능</p>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>빌드 완료</h2>
          <span className="metric-value">{metrics.built}</span>
          <p>빌드 처리 완료</p>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>게시됨</h2>
          <span className="metric-value">{metrics.published}</span>
          <a href="/registry">레지스트리에서 보기</a>
        </section>
      </div>
    </div>
  );
}
