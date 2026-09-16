"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useTranslations } from "@/i18n/I18nProvider";
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

function validationStatusKey(version: RegistryVersionSummary | null): string {
  if (!version) {
    return "registryDetail.unknown";
  }
  return ["validated", "approved", "published", "deprecated", "revoked"].includes(
    version.status,
  )
    ? "registryDetail.validated"
    : "registryDetail.pending";
}

function approvalStatusKey(version: RegistryVersionSummary | null): string {
  if (!version) {
    return "registryDetail.unknown";
  }
  return ["approved", "published", "deprecated", "revoked"].includes(version.status)
    ? "registryDetail.approved"
    : "registryDetail.pending";
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
  const t = useTranslations();
  const [copyStatus, setCopyStatus] = useState("");

  async function copyCommand(): Promise<void> {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(command);
      setCopyStatus(t("registryDetail.copied"));
    } catch {
      setCopyStatus(t("registryDetail.copyFailed"));
    }
  }

  return (
    <div className="finding-list">
      <pre className="manifest-block"><code>{command}</code></pre>
      <div className="actions-row">
        <button
          type="button"
          className="button-secondary button-compact"
          aria-label={t("registryDetail.copyAria", { title })}
          onClick={() => void copyCommand()}
        >
          {t("registryDetail.copyButton")}
        </button>
        <span className="muted" role="status">{copyStatus}</span>
      </div>
    </div>
  );
}

export function RegistryDetailPageContent({
  slug,
}: RegistryDetailPageContentProps) {
  const t = useTranslations();
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
          setError(cause instanceof ApiError ? cause.message : t("registryDetail.assetLoadError"));
        }
      }
    }

    void loadAsset();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
            cause instanceof ApiError ? cause.message : t("registryDetail.manifestLoadError"),
          );
        }
      }
    }

    void loadManifest();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        <p className="muted">{t("registryDetail.loadingAsset")}</p>
      </section>
    );
  }

  return (
    <div className="page-stack">
      <section className="workspace-panel design-hero">
        <div className="page-header">
          <div>
            <p className="eyebrow">{t("registryDetail.assetEyebrow")}</p>
            <h1 className="workspace-heading">{asset.name}</h1>
            <p className="page-description">{asset.slug}</p>
          </div>
          <StatusBadge label={asset.lifecycle} />
        </div>
        <p>{asset.description}</p>
        <p className="muted">
          {t("registryDetail.visibilityLabel", { visibility: asset.visibility })}
        </p>
      </section>

      {error ? <p className="error-text" role="alert">{error}</p> : null}

      <div className="registry-detail-grid">
      <section className="workspace-panel">
        <p className="eyebrow">{t("registryDetail.versionSelectEyebrow")}</p>
        <h2>{t("registryDetail.publishedVersionsHeading")}</h2>
        {versions.length === 0 ? (
          <p className="muted">{t("registryDetail.noPublishedVersions")}</p>
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
        <p className="eyebrow">{t("registryDetail.reviewBasisEyebrow")}</p>
        <h2>{t("registryDetail.releaseStatus")}</h2>
        {selectedVersion ? (
          <>
            <p>
              {t("registryDetail.versionWord")} <strong>{selectedVersion.version}</strong>
            </p>
            <p>
              <StatusBadge label={selectedVersion.status} />{" "}
              <StatusBadge label={selectedVersion.channel} />
            </p>
            <p className="digest-text">{selectedVersion.artifact_sha256}</p>
            <p className="muted">
              {t("registryDetail.validationLine", {
                status: t(validationStatusKey(selectedVersion)),
              })}
            </p>
            <p className="muted">
              {t("registryDetail.approvalLine", {
                status: t(approvalStatusKey(selectedVersion)),
              })}
            </p>
            <p>
              <a
                className="download-link"
                href={`/api/control-plane/registry/versions/${selectedVersion.id}/artifact`}
                download
              >
                {t("registryDetail.downloadArtifact")}
              </a>
            </p>
          </>
        ) : (
          <p className="muted">{t("registryDetail.noSelectedVersion")}</p>
        )}
      </section>
      </div>

      <section className="workspace-panel manifest-panel">
        <p className="eyebrow">{t("registryDetail.deployContractEyebrow")}</p>
        <h2>{t("registryDetail.immutableManifest")}</h2>
        {manifest ? (
          <div className="finding-list">
            <pre className="manifest-block">
              {JSON.stringify(toDisplayManifest(manifest), null, 2)}
            </pre>
          </div>
        ) : (
          <p className="muted">{t("registryDetail.manifestHint")}</p>
        )}
      </section>

      <section className="workspace-panel">
        <p className="eyebrow">{t("registryDetail.installEyebrow")}</p>
        <h2>{t("registryDetail.installHeading")}</h2>
        {selectedVersion ? (
          <>
            <p>{t("registryDetail.installIntro")}</p>
            <p className="muted">{t("registryDetail.installPlaceholderNote")}</p>
            {[
              {
                titleKey: "registryDetail.step1Title",
                descKey: "registryDetail.step1Desc",
                command: "curl -LsSf https://astral.sh/uv/install.sh | sh",
              },
              {
                titleKey: "registryDetail.step2Title",
                descKey: "registryDetail.step2Desc",
                command:
                  "uv run --frozen --no-config --extra cli hf login --registry <registry-url> --tenant <entra-tenant-id> --client-id <public-client-application-id> --scope api://<registry-api-app-id>/registry.access",
              },
              {
                titleKey: "registryDetail.step3Title",
                descKey: "registryDetail.step3Desc",
                command: `uv run --frozen --no-config --extra cli hf install ${asset.slug}@${selectedVersion.version} --target ../your-repository`,
              },
              {
                titleKey: "registryDetail.step4Title",
                descKey: "registryDetail.step4Desc",
                command: `uv run --frozen --no-config --extra cli hf install ${asset.slug}@${selectedVersion.version} --target ../your-repository --approve <preview-digest>`,
              },
              {
                titleKey: "registryDetail.step5Title",
                descKey: "registryDetail.step5Desc",
                command: "uv run --frozen --no-config --extra cli hf logout",
              },
            ].map((step, index) => (
              <div key={step.titleKey}>
                <h3>{index + 1}. {t(step.titleKey)}</h3>
                <p className="muted">{t(step.descKey)}</p>
                <InstallCommand key={step.command} title={t(step.titleKey)} command={step.command} />
              </div>
            ))}
            <p className="muted">{t("registryDetail.devLoginNote")}</p>
          </>
        ) : (
          <p className="muted">{t("registryDetail.installHint")}</p>
        )}
      </section>
    </div>
  );
}
