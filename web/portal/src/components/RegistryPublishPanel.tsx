"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api, apiRaw, ApiError } from "@/lib/api";
import type {
  HarnessDesign,
  RegistryActor,
  RegistryAssetCreate,
  RegistryAssetSummary,
  RegistryChannel,
  RegistryManifest,
  RegistryVersionDetail,
  RegistryVersionSummary,
} from "@/lib/types";

import styles from "./RegistryPublishPanel.module.css";

interface RegistryPublishPanelProps {
  design: HarnessDesign;
}

const SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const SEMVER_PATTERN = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/;

function workflowText(design: HarnessDesign, field: string): string {
  const value = design.workflow[field];
  return typeof value === "string" ? value.trim() : "";
}

function safeSlug(design: HarnessDesign): string {
  const workflowId = workflowText(design, "id");
  if (SLUG_PATTERN.test(workflowId)) {
    return workflowId;
  }
  return `${workflowId || design.name}`
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function defaultDescription(design: HarnessDesign): string {
  return workflowText(design, "goal") || design.name;
}

function safeError(cause: unknown, fallback: string): string {
  if (cause instanceof ApiError) {
    if (cause.status === 403) {
      return "이 작업에 필요한 역할이 없습니다. 조직 관리자에게 역할을 확인해 주세요.";
    }
    if (cause.code === "stale_digest") {
      return "설계 또는 버전 다이제스트가 변경되었습니다. 설계 상태를 새로고침한 뒤 다시 시도하세요.";
    }
    if (
      cause.code === "artifact_unavailable" ||
      cause.code === "artifact_corrupted"
    ) {
      return "검증된 빌드 산출물을 확인할 수 없습니다. 빌드를 다시 실행한 뒤 시도하세요.";
    }
    if (cause.code === "invalid_lifecycle") {
      return "현재 상태에서는 이 작업을 수행할 수 없습니다. 설계 빌드와 레지스트리 단계를 확인하세요.";
    }
  }
  return fallback;
}

function asVersionDetail(
  summary: RegistryVersionSummary,
  assetId: string,
  organizationId: string,
  manifest: RegistryManifest,
): RegistryVersionDetail {
  return {
    ...summary,
    asset_id: assetId,
    organization_id: organizationId,
    manifest,
  };
}

export function RegistryPublishPanel({ design }: RegistryPublishPanelProps) {
  const defaults = useMemo(
    () => ({
      slug: safeSlug(design),
      name: design.name,
      description: defaultDescription(design),
    }),
    [design.digest, design.id],
  );
  const [actor, setActor] = useState<RegistryActor | null>(null);
  const [assets, setAssets] = useState<RegistryAssetSummary[]>([]);
  const [ready, setReady] = useState(false);
  const [slug, setSlug] = useState(defaults.slug);
  const [name, setName] = useState(defaults.name);
  const [description, setDescription] = useState(defaults.description);
  const [versionNumber, setVersionNumber] = useState("1.0.0");
  const [channel, setChannel] =
    useState<Exclude<RegistryChannel, "unpublished">>("pilot");
  const [asset, setAsset] = useState<RegistryAssetSummary | null>(null);
  const [version, setVersion] = useState<RegistryVersionDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (design.status !== "built") {
      return;
    }
    let active = true;
    setActor(null);
    setAssets([]);
    setReady(false);
    setSlug(defaults.slug);
    setName(defaults.name);
    setDescription(defaults.description);
    setVersionNumber("1.0.0");
    setChannel("pilot");
    setAsset(null);
    setVersion(null);
    setMessage(null);
    setError(null);

    async function load(): Promise<void> {
      try {
        const [loadedActor, loadedAssets] = await Promise.all([
          api<RegistryActor>("/whoami"),
          api<RegistryAssetSummary[]>("/registry/assets?type=workflow"),
        ]);
        if (active) {
          setActor(loadedActor);
          setAssets(loadedAssets);
          setReady(true);
        }
      } catch {
        if (active) {
          setError(
            "레지스트리 연결 정보를 불러오지 못했습니다. 잠시 후 다시 시도하거나 권한을 확인해 주세요.",
          );
        }
      }
    }

    void load();
    return () => {
      active = false;
    };
  }, [defaults, design.digest, design.id, design.status]);

  if (design.status !== "built") {
    return null;
  }

  const slugValid = SLUG_PATTERN.test(slug);
  const versionValid = SEMVER_PATTERN.test(versionNumber);
  const roles = new Set(actor?.roles ?? []);
  const canManageAssets = roles.has("registry-admin");
  const canAuthor = roles.has("author") || roles.has("registry-admin");
  const canReview = roles.has("reviewer");
  const exactExistingAsset = assets.find((candidate) => candidate.slug === slug);

  function reset(): void {
    setSlug(defaults.slug);
    setName(defaults.name);
    setDescription(defaults.description);
    setVersionNumber("1.0.0");
    setChannel("pilot");
    setAsset(null);
    setVersion(null);
    setMessage(null);
    setError(null);
  }

  function selectExisting(exact: RegistryAssetSummary): boolean {
    if (
      exact.name !== name ||
      (exact.description ?? "") !== description
    ) {
      setError(
        "같은 슬러그의 기존 자산 이름 또는 설명이 입력값과 다릅니다. 기존 자산 정보를 확인하고 입력값을 맞추거나 다른 슬러그를 사용하세요.",
      );
      return false;
    }
    setAsset(exact);
    setMessage("기존 자산을 사용합니다.");
    return true;
  }

  async function prepareAsset(): Promise<void> {
    if (!actor || !slugValid || !name.trim() || !description.trim()) {
      setError("슬러그, 이름, 설명을 올바르게 입력해 주세요.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (exactExistingAsset) {
        selectExisting(exactExistingAsset);
        return;
      }
      try {
        const created = await api<RegistryAssetCreate>("/registry/assets", {
          method: "POST",
          body: {
            type: "workflow",
            slug,
            name: name.trim(),
            description: description.trim(),
            owner_subject_id: actor.subject_id,
          },
        });
        setAsset({ ...created, versions: [] });
        setMessage("자산 준비 완료");
      } catch (cause) {
        if (!(cause instanceof ApiError) || cause.status !== 409) {
          throw cause;
        }
        const refreshed = await api<RegistryAssetSummary[]>(
          "/registry/assets?type=workflow",
        );
        setAssets(refreshed);
        const conflicted = refreshed.find((candidate) => candidate.slug === slug);
        if (!conflicted || !selectExisting(conflicted)) {
          if (!conflicted) {
            setError(
              "자산 생성 충돌이 발생했지만 같은 슬러그를 다시 찾지 못했습니다. 목록을 새로고침한 뒤 다시 시도하세요.",
            );
          }
        }
      }
    } catch (cause) {
      setError(safeError(cause, "레지스트리 자산을 준비하지 못했습니다. 권한과 입력값을 확인해 주세요."));
    } finally {
      setBusy(false);
    }
  }

  async function recoverConflictingVersion(
    selectedAsset: RegistryAssetSummary,
    selectedVersionNumber: string,
    selectedName: string,
    selectedDescription: string,
    selectedDesignDigest: string,
    organizationId: string,
  ): Promise<boolean> {
    try {
      const refreshed = await api<RegistryAssetSummary[]>(
        "/registry/assets?type=workflow",
      );
      setAssets(refreshed);
      const refreshedAsset = refreshed.find(
        (candidate) =>
          candidate.id === selectedAsset.id &&
          candidate.slug === selectedAsset.slug,
      );
      if (!refreshedAsset) {
        setError(
          "버전 생성 충돌이 발생했지만 새로고침한 목록에서 같은 자산을 찾지 못했습니다. 자산 목록을 확인한 뒤 다시 시도하세요.",
        );
        return false;
      }
      setAsset(refreshedAsset);
      if (
        refreshedAsset.name !== selectedName ||
        (refreshedAsset.description ?? "") !== selectedDescription
      ) {
        setError(
          "버전 생성 충돌 후 다시 불러온 자산의 이름 또는 설명이 입력값과 다릅니다. 기존 자산 정보를 확인하거나 다른 슬러그를 사용하세요.",
        );
        return false;
      }
      const refreshedVersion = refreshedAsset.versions.find(
        (candidate) => candidate.version === selectedVersionNumber,
      );
      if (!refreshedVersion) {
        setError(
          `버전 생성 충돌이 발생했지만 새로고침한 자산에서 ${selectedVersionNumber} 버전을 찾지 못했습니다. 목록을 다시 확인한 뒤 재시도하세요.`,
        );
        return false;
      }
      const manifest = await apiRaw<RegistryManifest>(
        `/registry/versions/${refreshedVersion.id}/manifest`,
      );
      if (
        manifest.design_digest !== selectedDesignDigest ||
        manifest.artifact?.sha256 !== refreshedVersion.artifact_sha256
      ) {
        setError(
          `같은 ${selectedVersionNumber} 버전이 있지만 현재 설계와 일치하지 않습니다. 설계 또는 산출물 다이제스트를 확인하고 새 버전 번호를 입력하거나 기존 버전을 검토하세요.`,
        );
        return false;
      }
      setVersion(
        asVersionDetail(
          refreshedVersion,
          refreshedAsset.id,
          organizationId,
          manifest,
        ),
      );
      setMessage(
        `기존 ${selectedVersionNumber} 버전이 현재 설계와 일치해 다시 불러왔습니다.`,
      );
      return true;
    } catch {
      setError(
        "버전 생성 충돌 후 기존 버전을 다시 확인하지 못했습니다. 자산 목록과 매니페스트를 확인한 뒤 재시도하세요.",
      );
      return false;
    }
  }

  async function createVersion(): Promise<void> {
    if (!asset || !versionValid || design.status !== "built") {
      setError("빌드된 설계와 올바른 SemVer 버전이 필요합니다.");
      return;
    }
    const selectedAsset = asset;
    const selectedVersionNumber = versionNumber;
    const selectedName = name.trim();
    const selectedDescription = description.trim();
    const selectedDesignDigest = design.digest;
    const organizationId = actor?.organization_id ?? design.organization_id;
    setBusy(true);
    setError(null);
    try {
      const created = await api<RegistryVersionDetail>(
        `/registry/assets/${selectedAsset.id}/versions`,
        {
          method: "POST",
          body: {
            design_id: design.id,
            design_digest: selectedDesignDigest,
            version: selectedVersionNumber,
          },
        },
      );
      setVersion(created);
      setMessage("버전 생성 완료");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        await recoverConflictingVersion(
          selectedAsset,
          selectedVersionNumber,
          selectedName,
          selectedDescription,
          selectedDesignDigest,
          organizationId,
        );
      } else {
        setError(safeError(cause, "버전을 생성하지 못했습니다. 설계 빌드 상태와 버전 번호를 확인해 주세요."));
      }
    } finally {
      setBusy(false);
    }
  }

  async function reviewVersion(): Promise<void> {
    if (!version || version.status !== "draft") {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const reviewed = await api<RegistryVersionDetail>(
        `/registry/versions/${version.id}/reviews`,
        {
          method: "POST",
          body: {
            expected_digest: version.digest,
            decision: "approved",
          },
        },
      );
      setVersion(reviewed);
      setMessage("레지스트리 버전 승인 완료");
    } catch (cause) {
      setError(safeError(cause, "레지스트리 버전을 승인하지 못했습니다. 리뷰어 역할과 버전 상태를 확인해 주세요."));
    } finally {
      setBusy(false);
    }
  }

  async function publishVersion(): Promise<void> {
    if (!version || version.status !== "approved") {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const published = await api<RegistryVersionDetail>(
        `/registry/versions/${version.id}/publish`,
        {
          method: "POST",
          body: {
            expected_digest: version.digest,
            channel,
          },
        },
      );
      setVersion(published);
      setMessage(`${channel === "pilot" ? "파일럿" : "안정"} 채널 게시 완료`);
    } catch (cause) {
      setError(safeError(cause, "버전을 게시하지 못했습니다. 관리자 역할과 버전 상태를 확인해 주세요."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`workspace-panel ${styles.panel}`}>
      <div>
        <p className="eyebrow">Registry workflow</p>
        <h2>레지스트리 등록</h2>
        <p className={`muted ${styles.intro}`}>
          설계 다이제스트 승인과 레지스트리 버전 승인은 서로 다른 절차입니다.
          아래 단계에서 자산, 버전, 리뷰, 게시를 각각 확인하세요.
        </p>
      </div>

      <div className={styles.fields}>
        <label className="field">
          <span>레지스트리 슬러그</span>
          <input
            aria-label="레지스트리 슬러그"
            value={slug}
            disabled={Boolean(asset) || busy}
            onChange={(event) => setSlug(event.target.value)}
          />
          {!slugValid ? (
            <span className="field-error">
              소문자, 숫자, 하이픈만 사용하고 직접 수정해 주세요.
            </span>
          ) : null}
        </label>
        <label className="field">
          <span>이름</span>
          <input
            aria-label="레지스트리 이름"
            value={name}
            disabled={Boolean(asset) || busy}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className={`field ${styles.wide}`}>
          <span>설명</span>
          <textarea
            aria-label="레지스트리 설명"
            value={description}
            disabled={Boolean(asset) || busy}
            rows={2}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label className="field">
          <span>버전</span>
          <input
            aria-label="버전"
            value={versionNumber}
            disabled={Boolean(version) || busy}
            onChange={(event) => setVersionNumber(event.target.value)}
          />
          {!versionValid ? (
            <span className="field-error">MAJOR.MINOR.PATCH 형식이 필요합니다.</span>
          ) : null}
        </label>
        <label className="field">
          <span>배포 채널</span>
          <select
            aria-label="배포 채널"
            value={channel}
            disabled={version?.status === "published" || busy}
            onChange={(event) =>
              setChannel(event.target.value as "pilot" | "stable")
            }
          >
            <option value="pilot">pilot</option>
            <option value="stable">stable</option>
          </select>
        </label>
      </div>

      <ol className={styles.steps}>
        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>1. 자산 준비</h3>
            {asset ? <StatusBadge label="ready" /> : null}
          </div>
          <p className="muted">
            정확히 같은 슬러그를 재사용하거나 새 워크플로 자산을 만듭니다.
          </p>
          {!ready && !error ? <p className="muted">레지스트리 정보를 확인하는 중입니다.</p> : null}
          {ready ? (
            <div className="actions-row">
              <button
                className="button-secondary"
                type="button"
                disabled={
                  busy ||
                  Boolean(asset) ||
                  !slugValid ||
                  !name.trim() ||
                  !description.trim() ||
                  (!exactExistingAsset && !canManageAssets)
                }
                onClick={() => void prepareAsset()}
              >
                자산 준비
              </button>
              {asset ? (
                <button
                  className="button-secondary"
                  type="button"
                  disabled={busy}
                  onClick={reset}
                >
                  등록 흐름 초기화
                </button>
              ) : null}
            </div>
          ) : null}
        </li>

        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>2. 버전 생성</h3>
            {version ? <StatusBadge label={version.status} /> : null}
          </div>
          <p className="muted">
            현재 설계 ID와 다이제스트를 검증된 빌드 산출물에 연결합니다.
          </p>
          <button
            className="button-secondary"
            type="button"
            disabled={busy || !asset || Boolean(version) || !versionValid || !canAuthor}
            onClick={() => void createVersion()}
          >
            버전 생성
          </button>
          {version ? (
            <dl className={styles.details}>
              <div><dt>버전 다이제스트</dt><dd><code>{version.digest}</code></dd></div>
              <div><dt>상태</dt><dd>{version.status}</dd></div>
              <div><dt>산출물 SHA-256</dt><dd><code>{version.artifact_sha256}</code></dd></div>
            </dl>
          ) : null}
        </li>

        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>3. 레지스트리 버전 리뷰</h3>
          </div>
          <p className="muted">
            설계 승인과 별개로 초안 레지스트리 버전을 리뷰어가 명시적으로 승인합니다.
          </p>
          <button
            className="button-secondary"
            type="button"
            disabled={busy || version?.status !== "draft" || !canReview}
            onClick={() => void reviewVersion()}
          >
            레지스트리 버전 승인
          </button>
        </li>

        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>4. 채널 게시</h3>
          </div>
          <p className="muted">승인된 버전을 선택한 채널에 명시적으로 게시합니다.</p>
          <button
            className="button-primary"
            type="button"
            disabled={busy || version?.status !== "approved" || !canManageAssets}
            onClick={() => void publishVersion()}
          >
            게시
          </button>
          {version?.status === "published" ? (
            <a href={`/registry/${slug}`}>레지스트리에서 보기</a>
          ) : null}
        </li>
      </ol>

      {actor && (!canManageAssets || !canAuthor || !canReview) ? (
        <p className="muted">
          일부 단계에 필요한 author, reviewer 또는 registry-admin 역할이 없습니다.
        </p>
      ) : null}
      {message ? <p className="save-state" role="status">{message}</p> : null}
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </section>
  );
}
