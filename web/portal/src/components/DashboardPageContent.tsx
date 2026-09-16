"use client";

import { useEffect, useMemo, useState } from "react";

import { useLocale, useTranslations } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import type { ContentLanguage, HarnessDesign, RegistryAssetSummary } from "@/lib/types";

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
  locale: ContentLanguage,
): DashboardMetrics {
  const localeDesigns = designs.filter((design) => design.language === locale);
  const localeAssets = assets.filter((asset) => asset.language === locale);
  return {
    totalDesigns: localeDesigns.length,
    validated: localeDesigns.filter((design) => design.status === "validated").length,
    approved: localeDesigns.filter((design) => design.status === "approved").length,
    built: localeDesigns.filter((design) => design.status === "built").length,
    published: localeAssets.reduce(
      (count, asset) =>
        count +
        asset.versions.filter((version) => version.status === "published").length,
      0,
    ),
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
      <section className="workspace-panel state-panel" aria-busy="true">
        <p className="eyebrow">{t("dashboard.loadingEyebrow")}</p>
        <h1 className="workspace-heading">{t("dashboard.loadingHeading")}</h1>
      </section>
    );
  }

  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">{t("dashboard.introEyebrow")}</p>
        <h1 className="workspace-heading">{t("dashboard.introHeading")}</h1>
        <p className="page-description">{t("dashboard.introDescription")}</p>
      </header>
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
    </div>
  );
}
