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
            cause instanceof ApiError ? cause.message : "Unable to load dashboard data.",
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
    return <p className="error-text">{error}</p>;
  }

  if (!metrics) {
    return <p className="muted">Loading dashboard…</p>;
  }

  return (
    <div className="cards-grid">
      <section className="card">
        <h2>Total designs</h2>
        <span className="metric-value">{metrics.totalDesigns}</span>
      </section>
      <section className="card">
        <h2>Validated</h2>
        <span className="metric-value">{metrics.validated}</span>
      </section>
      <section className="card">
        <h2>Approved</h2>
        <span className="metric-value">{metrics.approved}</span>
      </section>
      <section className="card">
        <h2>Built</h2>
        <span className="metric-value">{metrics.built}</span>
      </section>
      <section className="card">
        <h2>Published</h2>
        <span className="metric-value">{metrics.published}</span>
      </section>
    </div>
  );
}
