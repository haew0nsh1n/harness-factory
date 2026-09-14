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
    return "Unknown";
  }
  return ["validated", "approved", "published", "deprecated", "revoked"].includes(
    version.status,
  )
    ? "Validated"
    : "Pending";
}

function approvalStatus(version: RegistryVersionSummary | null): string {
  if (!version) {
    return "Unknown";
  }
  return ["approved", "published", "deprecated", "revoked"].includes(version.status)
    ? "Approved"
    : "Pending";
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
          setError(cause instanceof ApiError ? cause.message : "Unable to load asset.");
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
          setError(cause instanceof ApiError ? cause.message : "Unable to load manifest.");
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
    return <p className="muted">Loading asset…</p>;
  }

  return (
    <div className="detail-grid">
      <section className="card">
        <div className="page-header">
          <div>
            <h1>{asset.name}</h1>
            <p className="muted">{asset.slug}</p>
          </div>
          <StatusBadge label={asset.lifecycle} />
        </div>
        <p>{asset.description}</p>
        <p className="muted">Visibility: {asset.visibility}</p>
      </section>

      <section className="card">
        <h2>Published versions</h2>
        {versions.length === 0 ? (
          <p className="muted">No published versions.</p>
        ) : (
          <div className="finding-list">
            {versions.map((version) => (
              <button
                key={version.id}
                type="button"
                onClick={() => setSelectedVersionId(version.id)}
              >
                {version.version} · {version.channel}
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2>Release status</h2>
        {selectedVersion ? (
          <>
            <p>
              Version <strong>{selectedVersion.version}</strong>
            </p>
            <p>
              <StatusBadge label={selectedVersion.status} />{" "}
              <StatusBadge label={selectedVersion.channel} />
            </p>
            <p className="digest-text">{selectedVersion.artifact_sha256}</p>
            <p className="muted">Validation: {validationStatus(selectedVersion)}</p>
            <p className="muted">Approval: {approvalStatus(selectedVersion)}</p>
          </>
        ) : (
          <p className="muted">No released version selected.</p>
        )}
      </section>

      <section className="card">
        <h2>Immutable manifest summary</h2>
        {manifest ? (
          <div className="finding-list">
            <pre className="manifest-block">
              {JSON.stringify(toDisplayManifest(manifest), null, 2)}
            </pre>
          </div>
        ) : (
          <p className="muted">Select a published version to view its manifest summary.</p>
        )}
      </section>
    </div>
  );
}
