"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { type TranslateFn } from "@/i18n/dictionaries";
import { useTranslations } from "@/i18n/I18nProvider";
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

function safeError(cause: unknown, fallback: string, t: TranslateFn): string {
  if (cause instanceof ApiError) {
    if (cause.status === 403) {
      return t("publish.role403");
    }
    if (cause.code === "stale_digest") {
      return t("publish.staleDigest");
    }
    if (
      cause.code === "artifact_unavailable" ||
      cause.code === "artifact_corrupted"
    ) {
      return t("publish.artifactUnavailable");
    }
    if (cause.code === "invalid_lifecycle") {
      return t("publish.invalidLifecycle");
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
  const t = useTranslations();
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
          setError(t("publish.connectionError"));
        }
      }
    }

    void load();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defaults, design.digest, design.id, design.status]);

  const slugValid = SLUG_PATTERN.test(slug);
  const versionValid = SEMVER_PATTERN.test(versionNumber);
  const isBuilt = design.status === "built";
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
      setError(t("publish.nameMismatch"));
      return false;
    }
    setAsset(exact);
    setMessage(t("publish.useExisting"));
    return true;
  }

  async function prepareAsset(): Promise<void> {
    if (!actor || !slugValid || !name.trim() || !description.trim()) {
      setError(t("publish.invalidInput"));
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
            language: design.language,
            description: description.trim(),
            owner_subject_id: actor.subject_id,
          },
        });
        setAsset({ ...created, versions: [] });
        setMessage(t("publish.assetReady"));
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
            setError(t("publish.conflictNotFound"));
          }
        }
      }
    } catch (cause) {
      setError(safeError(cause, t("publish.prepareFailed"), t));
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
        setError(t("publish.assetNotFoundAfterConflict"));
        return false;
      }
      setAsset(refreshedAsset);
      if (
        refreshedAsset.name !== selectedName ||
        (refreshedAsset.description ?? "") !== selectedDescription
      ) {
        setError(t("publish.assetMismatchAfterConflict"));
        return false;
      }
      const refreshedVersion = refreshedAsset.versions.find(
        (candidate) => candidate.version === selectedVersionNumber,
      );
      if (!refreshedVersion) {
        setError(
          t("publish.versionNotFoundAfterConflict", { version: selectedVersionNumber }),
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
          t("publish.versionMismatch", { version: selectedVersionNumber }),
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
        t("publish.versionRecovered", { version: selectedVersionNumber }),
      );
      return true;
    } catch {
      setError(t("publish.recoverFailed"));
      return false;
    }
  }

  async function createVersion(): Promise<void> {
    if (!asset || !versionValid || design.status !== "built") {
      setError(t("publish.needBuiltVersion"));
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
      setMessage(t("publish.versionCreated"));
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
        setError(safeError(cause, t("publish.createVersionFailed"), t));
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
      setMessage(t("publish.versionApproved"));
    } catch (cause) {
      setError(safeError(cause, t("publish.reviewFailed"), t));
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
      setMessage(
        t("publish.publishedChannel", {
          channel: t(channel === "pilot" ? "registry.channelPilot" : "registry.channelStable"),
        }),
      );
    } catch (cause) {
      setError(safeError(cause, t("publish.publishFailed"), t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`workspace-panel ${styles.panel}`}>
      <div>
        <p className="eyebrow">{t("publish.eyebrow")}</p>
        <h2>{t("publish.heading")}</h2>
        <p className={`muted ${styles.intro}`}>{t("publish.intro")}</p>
        {!isBuilt ? (
          <p className="save-state" role="status">
            {t("publish.needBuiltNotice")}
          </p>
        ) : null}
      </div>

      <div className={styles.fields}>
        <label className="field">
          <span>{t("publish.slugLabel")}</span>
          <input
            aria-label={t("publish.slugLabel")}
            value={slug}
            disabled={Boolean(asset) || busy}
            onChange={(event) => setSlug(event.target.value)}
          />
          {!slugValid ? (
            <span className="field-error">{t("publish.slugError")}</span>
          ) : null}
        </label>
        <label className="field">
          <span>{t("publish.nameLabel")}</span>
          <input
            aria-label={t("publish.nameAria")}
            value={name}
            disabled={Boolean(asset) || busy}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className={`field ${styles.wide}`}>
          <span>{t("publish.descLabel")}</span>
          <textarea
            aria-label={t("publish.descAria")}
            value={description}
            disabled={Boolean(asset) || busy}
            rows={2}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label className="field">
          <span>{t("publish.versionLabel")}</span>
          <input
            aria-label={t("publish.versionLabel")}
            value={versionNumber}
            disabled={Boolean(version) || busy}
            onChange={(event) => setVersionNumber(event.target.value)}
          />
          {!versionValid ? (
            <span className="field-error">{t("publish.versionError")}</span>
          ) : null}
        </label>
        <label className="field">
          <span>{t("registry.channelLabel")}</span>
          <select
            aria-label={t("registry.channelLabel")}
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
            <h3>1. {t("publish.step1Title")}</h3>
            {asset ? <StatusBadge label="ready" /> : null}
          </div>
          <p className="muted">{t("publish.step1Desc")}</p>
          {!ready && !error ? <p className="muted">{t("publish.checkingRegistry")}</p> : null}
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
                {t("publish.prepareAssetBtn")}
              </button>
              {asset ? (
                <button
                  className="button-secondary"
                  type="button"
                  disabled={busy}
                  onClick={reset}
                >
                  {t("publish.resetFlow")}
                </button>
              ) : null}
            </div>
          ) : null}
        </li>

        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>2. {t("publish.step2Title")}</h3>
            {version ? <StatusBadge label={version.status} /> : null}
          </div>
          <p className="muted">{t("publish.step2Desc")}</p>
          <button
            className="button-secondary"
            type="button"
            disabled={busy || !asset || Boolean(version) || !versionValid || !canAuthor || !isBuilt}
            onClick={() => void createVersion()}
          >
            {t("publish.createVersionBtn")}
          </button>
          {version ? (
            <dl className={styles.details}>
              <div><dt>{t("publish.versionDigest")}</dt><dd><code>{version.digest}</code></dd></div>
              <div><dt>{t("publish.statusLabel")}</dt><dd>{version.status}</dd></div>
              <div><dt>{t("publish.artifactSha")}</dt><dd><code>{version.artifact_sha256}</code></dd></div>
            </dl>
          ) : null}
        </li>

        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>3. {t("publish.step3Title")}</h3>
          </div>
          <p className="muted">{t("publish.step3Desc")}</p>
          <button
            className="button-secondary"
            type="button"
            disabled={busy || version?.status !== "draft" || !canReview}
            onClick={() => void reviewVersion()}
          >
            {t("publish.approveVersionBtn")}
          </button>
        </li>

        <li className={styles.step}>
          <div className={styles.stepHeader}>
            <h3>4. {t("publish.step4Title")}</h3>
          </div>
          <p className="muted">{t("publish.step4Desc")}</p>
          <button
            className="button-primary"
            type="button"
            disabled={busy || version?.status !== "approved" || !canManageAssets}
            onClick={() => void publishVersion()}
          >
            {t("publish.publishBtn")}
          </button>
          {version?.status === "published" ? (
            <a href={`/registry/${slug}`}>{t("publish.viewInRegistry")}</a>
          ) : null}
        </li>
      </ol>

      {actor && (!canManageAssets || !canAuthor || !canReview) ? (
        <p className="muted">{t("publish.missingRoles")}</p>
      ) : null}
      {message ? <p className="save-state" role="status">{message}</p> : null}
      {error ? <p className="error-text" role="alert">{error}</p> : null}
    </section>
  );
}
