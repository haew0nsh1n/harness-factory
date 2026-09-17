"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useLocale, useTranslations } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import type {
  ContentLanguage,
  DesignStatus,
  HarnessDesign,
  RegistryAssetSummary,
} from "@/lib/types";

const PIPELINE_ORDER: DesignStatus[] = [
  "draft",
  "validated",
  "approved",
  "build-queued",
  "built",
  "failed",
];

interface DashboardMetrics {
  totalDesigns: number;
  validated: number;
  approved: number;
  built: number;
  published: number;
  statusCounts: Record<DesignStatus, number>;
  attention: {
    failed: number;
    withFindings: number;
    buildQueued: number;
    draft: number;
  };
  recent: HarnessDesign[];
}

function relativeTime(iso: string, locale: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) {
    return "";
  }
  const diffSeconds = Math.round((then - Date.now()) / 1000);
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ["year", 31536000],
    ["month", 2592000],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, seconds] of units) {
    if (Math.abs(diffSeconds) >= seconds) {
      return formatter.format(Math.round(diffSeconds / seconds), unit);
    }
  }
  return formatter.format(diffSeconds, "second");
}

function summarizeMetrics(
  designs: HarnessDesign[],
  assets: RegistryAssetSummary[],
  locale: ContentLanguage,
): DashboardMetrics {
  const localeDesigns = designs.filter((design) => design.language === locale);
  const localeAssets = assets.filter((asset) => asset.language === locale);
  const statusCounts = PIPELINE_ORDER.reduce(
    (counts, status) => ({ ...counts, [status]: 0 }),
    {} as Record<DesignStatus, number>,
  );
  for (const design of localeDesigns) {
    if (design.status in statusCounts) {
      statusCounts[design.status] += 1;
    }
  }
  const withFindings = localeDesigns.filter(
    (design) => (design.validation_findings?.length ?? 0) > 0,
  ).length;
  const recent = [...localeDesigns]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, 5);
  return {
    totalDesigns: localeDesigns.length,
    validated: statusCounts.validated,
    approved: statusCounts.approved,
    built: statusCounts.built,
    published: localeAssets.reduce(
      (count, asset) =>
        count +
        asset.versions.filter((version) => version.status === "published").length,
      0,
    ),
    statusCounts,
    attention: {
      failed: statusCounts.failed,
      withFindings,
      buildQueued: statusCounts["build-queued"],
      draft: statusCounts.draft,
    },
    recent,
  };
}

export function DashboardPageContent() {
  const t = useTranslations();
  const locale = useLocale();
  const [designs, setDesigns] = useState<HarnessDesign[] | null>(null);
  const [assets, setAssets] = useState<RegistryAssetSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        const [loadedDesigns, loadedAssets] = await Promise.all([
          api<HarnessDesign[]>("/designs"),
          api<RegistryAssetSummary[]>("/registry/assets?type=workflow"),
        ]);
        if (active) {
          setDesigns(loadedDesigns);
          setAssets(loadedAssets);
        }
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof ApiError
              ? cause.message
              : t("dashboard.loadError"),
          );
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const metrics = useMemo<DashboardMetrics | null>(
    () =>
      designs && assets
        ? summarizeMetrics(designs, assets, locale as ContentLanguage)
        : null,
    [designs, assets, locale],
  );

  if (error) {
    return (
      <section className="workspace-panel state-panel" role="alert">
        <p className="eyebrow">{t("dashboard.errorEyebrow")}</p>
        <h1 className="workspace-heading">{t("dashboard.errorHeading")}</h1>
        <p className="error-text">{error}</p>
      </section>
    );
  }

  if (!metrics) {
    return (
      <p className="operation-status" role="status" aria-live="polite">
        <span className="operation-dots" aria-hidden="true">
          •••
        </span>
        {t("dashboard.loadingHeading")}
      </p>
    );
  }

  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">{t("dashboard.introEyebrow")}</p>
        <h3 className="workspace-heading">{t("dashboard.introHeading")}</h3>
        <p className="page-description">{t("dashboard.introDescription")}</p>
      </header>

      <section className="workspace-panel">
        <p className="eyebrow">{t("dashboard.attentionEyebrow")}</p>
        <h2>{t("dashboard.attentionHeading")}</h2>
        <div className="attention-grid">
          <div className="attention-card attention-error">
            <span className="attention-value">{metrics.attention.failed}</span>
            <span className="attention-label">{t("dashboard.attentionFailed")}</span>
            <span className="attention-hint">{t("dashboard.attentionFailedHint")}</span>
          </div>
          <div className="attention-card attention-warn">
            <span className="attention-value">{metrics.attention.withFindings}</span>
            <span className="attention-label">{t("dashboard.attentionFindings")}</span>
            <span className="attention-hint">{t("dashboard.attentionFindingsHint")}</span>
          </div>
          <div className="attention-card attention-info">
            <span className="attention-value">{metrics.attention.buildQueued}</span>
            <span className="attention-label">{t("dashboard.attentionBuildQueued")}</span>
            <span className="attention-hint">{t("dashboard.attentionBuildQueuedHint")}</span>
          </div>
          <div className="attention-card attention-muted">
            <span className="attention-value">{metrics.attention.draft}</span>
            <span className="attention-label">{t("dashboard.attentionDraft")}</span>
            <span className="attention-hint">{t("dashboard.attentionDraftHint")}</span>
          </div>
        </div>
      </section>

      <div className="status-overview">
        <section className="workspace-panel metric-panel">
          <h2>{t("dashboard.metricTotal")}</h2>
          <span className="metric-value">{metrics.totalDesigns}</span>
          <a href="/studio">{t("dashboard.viewDesigns")}</a>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>{t("dashboard.metricValidated")}</h2>
          <span className="metric-value">{metrics.validated}</span>
          <p>{t("dashboard.validatedHint")}</p>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>{t("dashboard.metricApproved")}</h2>
          <span className="metric-value">{metrics.approved}</span>
          <p>{t("dashboard.approvedHint")}</p>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>{t("dashboard.metricBuilt")}</h2>
          <span className="metric-value">{metrics.built}</span>
          <p>{t("dashboard.builtHint")}</p>
        </section>
        <section className="workspace-panel metric-panel">
          <h2>{t("dashboard.metricPublished")}</h2>
          <span className="metric-value">{metrics.published}</span>
          <a href="/registry">{t("dashboard.viewInRegistry")}</a>
        </section>
      </div>

      <section className="workspace-panel">
        <p className="eyebrow">{t("dashboard.pipelineEyebrow")}</p>
        <h2>{t("dashboard.pipelineHeading")}</h2>
        {metrics.totalDesigns === 0 ? (
          <p className="muted">{t("dashboard.pipelineEmpty")}</p>
        ) : (
          <>
            <div
              className="pipeline-bar"
              role="img"
              aria-label={t("dashboard.pipelineHeading")}
            >
              {PIPELINE_ORDER.filter((status) => metrics.statusCounts[status] > 0).map(
                (status) => (
                  <span
                    key={status}
                    className={`pipeline-seg pipeline-${status}`}
                    style={{
                      width: `${(metrics.statusCounts[status] / metrics.totalDesigns) * 100}%`,
                    }}
                    title={`${t(`status.${status}`)}: ${metrics.statusCounts[status]}`}
                  />
                ),
              )}
            </div>
            <ul className="pipeline-legend">
              {PIPELINE_ORDER.map((status) => (
                <li key={status} className="pipeline-legend-item">
                  <span className={`pipeline-dot pipeline-${status}`} />
                  {t(`status.${status}`)} <strong>{metrics.statusCounts[status]}</strong>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="workspace-panel">
        <p className="eyebrow">{t("dashboard.recentEyebrow")}</p>
        <h2>{t("dashboard.recentHeading")}</h2>
        {metrics.recent.length === 0 ? (
          <p className="muted">{t("dashboard.recentEmpty")}</p>
        ) : (
          <ul className="recent-list">
            {metrics.recent.map((design) => (
              <li key={design.id} className="recent-item">
                <a href={`/studio/${design.id}`} className="recent-name">
                  {design.name}
                </a>
                <StatusBadge label={design.status} />
                <span className="muted recent-time">
                  {relativeTime(design.updated_at, locale)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
