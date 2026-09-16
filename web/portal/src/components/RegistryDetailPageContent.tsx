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

function InstallCommand({ title, command }: { title: string; command: string }) {
  const [copyStatus, setCopyStatus] = useState("");

  async function copyCommand(): Promise<void> {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(command);
      setCopyStatus("복사했습니다.");
    } catch {
      setCopyStatus("복사하지 못했습니다. 명령을 직접 선택해 복사해 주세요.");
    }
  }

  return (
    <div className="finding-list">
      <pre className="manifest-block"><code>{command}</code></pre>
      <div className="actions-row">
        <button
          type="button"
          className="button-secondary button-compact"
          aria-label={`${title} 명령 복사`}
          onClick={() => void copyCommand()}
        >
          복사
        </button>
        <span className="muted" role="status">{copyStatus}</span>
      </div>
    </div>
  );
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

      <section className="workspace-panel">
        <p className="eyebrow">설치</p>
        <h2>로컬에 설치하기</h2>
        {selectedVersion ? (
          <>
            <p>
              harness-factory 저장소를 로컬에 체크아웃한 뒤, pyproject.toml과 uv.lock이
              있는 저장소 루트에서 아래 hf 명령을 순서대로 실행하세요.
              설치 대상은 별도의 로컬 저장소입니다.
            </p>
            <p className="muted">
              &lt;...&gt; 자리표시자는 꺾쇠까지 실제 값으로 바꾸고,
              ../your-repository는 설치할 저장소 경로로 바꾸세요.
              공백이 있는 경로는 따옴표로 감싸세요.
            </p>
            {[
              {
                title: "uv 준비",
                description:
                  "uv가 없다면 macOS/Linux 또는 WSL의 sh 환경에서 Astral 공식 설치 프로그램을 실행하세요. 설치 후 터미널을 다시 열고 저장소 루트로 이동하세요.",
                command: "curl -LsSf https://astral.sh/uv/install.sh | sh",
              },
              {
                title: "Registry 로그인",
                description:
                  "관리자에게 Registry URL, Entra tenant ID, device code flow가 허용된 public-client 앱 ID와 Registry API delegated scope를 확인하세요. 토큰 저장에는 지원되는 네이티브 OS keyring이 필요합니다.",
                command:
                  "uv run --frozen --no-config --extra cli hf login --registry <registry-url> --tenant <entra-tenant-id> --client-id <public-client-application-id> --scope api://<registry-api-app-id>/registry.access",
              },
              {
                title: "변경 미리보기",
                description:
                  "설치 대상 파일은 변경하지 않습니다. 출력되는 파일 작업, 로컬 텍스트 diff와 승인용 preview digest를 검토하세요.",
                command: `uv run --frozen --no-config --extra cli hf install ${asset.slug}@${selectedVersion.version} --target ../your-repository`,
              },
              {
                title: "설치 적용",
                description:
                  "--approve의 <preview-digest>에는 바로 앞 미리보기 명령이 출력한 승인용 digest를 넣으세요. 이 값은 대상 저장소의 파일 변경 계획으로 계산되며, 이 페이지의 artifact_sha256이나 design_digest가 아닙니다. 같은 대상 경로를 사용하고, 파일 상태가 달라졌다면 미리보기를 다시 실행하세요.",
                command: `uv run --frozen --no-config --extra cli hf install ${asset.slug}@${selectedVersion.version} --target ../your-repository --approve <preview-digest>`,
              },
              {
                title: "로그아웃",
                description: "작업을 마치면 저장된 로그인 정보를 지우세요.",
                command: "uv run --frozen --no-config --extra cli hf logout",
              },
            ].map((step, index) => (
              <div key={step.title}>
                <h3>{index + 1}. {step.title}</h3>
                <p className="muted">{step.description}</p>
                <InstallCommand key={step.command} title={step.title} command={step.command} />
              </div>
            ))}
            <p className="muted">
              로컬 개발용 로그인에는 --development --organization ... --subject ... --role ...
              옵션이 있으며, DNS 이름이 아닌 loopback IP origin에서만 사용할 수 있습니다.
            </p>
          </>
        ) : (
          <p className="muted">게시된 버전을 선택하면 설치 명령을 표시합니다.</p>
        )}
      </section>
    </div>
  );
}
