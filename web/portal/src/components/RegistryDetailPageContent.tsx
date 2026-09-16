"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api, apiRaw, ApiError } from "@/lib/api";
import type {
  RegistryAssetDetail,
  RegistryManifest,
  RegistryVersionSummary,
} from "@/lib/types";

interface RegistryDetailPageContentProps {
  slug: string;
}

interface DisplayManifest {
  schema_version: number;
  asset: {
    type: string;
    slug: string;
  };
  version: string;
  runtime: string;
  design_digest: string;
  artifact_sha256: string;
  dependencies: unknown[];
}

function publishedVersions(asset: RegistryAssetDetail | null): RegistryVersionSummary[] {
  return (asset?.versions ?? []).filter((version) => version.status === "published");
}

function validationStatus(version: RegistryVersionSummary | null): string {
  if (!version) {
    return "알 수 없음";
  }
  return ["validated", "approved", "published", "deprecated", "revoked"].includes(
    version.status,
  )
    ? "검증됨"
    : "대기 중";
}

function approvalStatus(version: RegistryVersionSummary | null): string {
  if (!version) {
    return "알 수 없음";
  }
  return ["approved", "published", "deprecated", "revoked"].includes(version.status)
    ? "승인됨"
    : "대기 중";
}

function toDisplayManifest(manifest: RegistryManifest): DisplayManifest {
  return {
    schema_version: manifest.schema_version,
    asset: {
      type: manifest.asset.type,
      slug: manifest.asset.slug,
    },
    version: manifest.version,
    runtime: manifest.runtime,
    design_digest: manifest.design_digest,
    artifact_sha256: manifest.artifact.sha256,
    dependencies: manifest.dependencies,
  };
}

export function RegistryDetailPageContent({
  slug,
}: RegistryDetailPageContentProps) {
  const [asset, setAsset] = useState<RegistryAssetDetail | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [manifest, setManifest] = useState<RegistryManifest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadAsset(): Promise<void> {
      try {
        const loaded = await api<RegistryAssetDetail>(`/registry/assets/${slug}`);
        if (active) {
          const versions = publishedVersions(loaded);
          setAsset(loaded);
          setSelectedVersionId(versions[0]?.id ?? null);
          setError(null);
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : "자산을 불러오지 못했습니다.");
        }
      }
    }

    void loadAsset();

    return () => {
      active = false;
    };
  }, [slug]);

  useEffect(() => {
    let active = true;

    async function loadManifest(): Promise<void> {
      if (!selectedVersionId) {
        setManifest(null);
        return;
      }

      try {
        const loaded = await apiRaw<RegistryManifest>(
          `/registry/versions/${selectedVersionId}/manifest`,
        );
        if (active) {
          setManifest(loaded);
          setError(null);
        }
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof ApiError ? cause.message : "매니페스트를 불러오지 못했습니다.",
          );
        }
      }
    }

    void loadManifest();

    return () => {
      active = false;
    };
  }, [selectedVersionId]);

  const versions = useMemo(() => publishedVersions(asset), [asset]);
  const selectedVersion =
    versions.find((version) => version.id === selectedVersionId) ?? versions[0] ?? null;

  if (error && !asset) {
    return <p className="error-text">{error}</p>;
  }

  if (!asset) {
    return (
      <section className="workspace-panel state-panel" aria-busy="true">
        <p className="muted">자산을 불러오는 중입니다.</p>
      </section>
    );
  }

  return (
    <div className="page-stack">
      <section className="workspace-panel design-hero">
        <div className="page-header">
          <div>
            <p className="eyebrow">워크플로 자산</p>
            <h1 className="workspace-heading">{asset.name}</h1>
            <p className="page-description">{asset.slug}</p>
          </div>
          <StatusBadge label={asset.lifecycle} />
        </div>
        <p>{asset.description}</p>
        <p className="muted">공개 범위: {asset.visibility}</p>
      </section>

      {error ? <p className="error-text" role="alert">{error}</p> : null}

      <div className="registry-detail-grid">
      <section className="workspace-panel">
        <p className="eyebrow">버전 선택</p>
        <h2>게시 버전</h2>
        {versions.length === 0 ? (
          <p className="muted">게시된 버전이 없습니다.</p>
        ) : (
          <div className="version-list">
            {versions.map((version) => (
              <button
                className="version-button"
                key={version.id}
                type="button"
                onClick={() => setSelectedVersionId(version.id)}
                aria-pressed={selectedVersion?.id === version.id}
              >
                <span>{version.version}</span>
                <StatusBadge label={version.channel} />
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-panel">
        <p className="eyebrow">검토 근거</p>
        <h2>릴리스 상태</h2>
        {selectedVersion ? (
          <>
            <p>
              버전 <strong>{selectedVersion.version}</strong>
            </p>
            <p>
              <StatusBadge label={selectedVersion.status} />{" "}
              <StatusBadge label={selectedVersion.channel} />
            </p>
            <p className="digest-text">{selectedVersion.artifact_sha256}</p>
            <p className="muted">검증: {validationStatus(selectedVersion)}</p>
            <p className="muted">승인: {approvalStatus(selectedVersion)}</p>
          </>
        ) : (
          <p className="muted">선택된 게시 버전이 없습니다.</p>
        )}
      </section>
      </div>

      <section className="workspace-panel manifest-panel">
        <p className="eyebrow">배포 계약</p>
        <h2>변경 불가 매니페스트</h2>
        {manifest ? (
          <div className="finding-list">
            <pre className="manifest-block">
              {JSON.stringify(toDisplayManifest(manifest), null, 2)}
            </pre>
          </div>
        ) : (
          <p className="muted">게시 버전을 선택하면 매니페스트 요약을 표시합니다.</p>
        )}
      </section>
    </div>
  );
}
