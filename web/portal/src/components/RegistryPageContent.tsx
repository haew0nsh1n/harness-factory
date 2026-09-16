"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useLocale, useTranslations } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import type {
  RegistryAssetSummary,
  RegistryChannel,
  RegistryVersionSummary,
} from "@/lib/types";

function onlyPublishedVersions(asset: RegistryAssetSummary): RegistryVersionSummary[] {
  return asset.versions.filter((version) => version.status === "published");
}

export function RegistryPageContent() {
  const t = useTranslations();
  const locale = useLocale();
  const [items, setItems] = useState<RegistryAssetSummary[]>([]);
  const [query, setQuery] = useState("");
  const [channel, setChannel] = useState<"" | Exclude<RegistryChannel, "unpublished">>("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      const params = new URLSearchParams({ type: "workflow" });
      if (query) {
        params.set("query", query);
      }
      if (channel) {
        params.set("channel", channel);
      }

      try {
        const results = await api<RegistryAssetSummary[]>(
          `/registry/assets?${params.toString()}`,
        );
        if (active) {
          setItems(results);
          setError(null);
        }
      } catch (cause) {
        if (active) {
          setError(
            cause instanceof ApiError
              ? cause.message
              : t("registry.loadError"),
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    void load();

    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, query]);

  const visibleItems = useMemo(
    () =>
      items
        .filter((item) => item.language === locale)
        .map((item) => ({ ...item, versions: onlyPublishedVersions(item) }))
        .filter((item) => item.versions.length > 0),
    [items, locale],
  );

  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">{t("registry.eyebrow")}</p>
        <h1 className="workspace-heading">{t("registry.heading")}</h1>
        <p className="page-description">{t("registry.description")}</p>
      </header>
      <div className="workspace-panel filter-panel">
        <label className="field">
          <span>{t("registry.searchLabel")}</span>
          <input
            type="search"
            aria-label={t("registry.searchLabel")}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("registry.searchPlaceholder")}
          />
        </label>
        <label className="field">
          <span>{t("registry.channelLabel")}</span>
          <select
            aria-label={t("registry.channelLabel")}
            value={channel}
            onChange={(event) =>
              setChannel(event.target.value as "" | "pilot" | "stable")
            }
          >
            <option value="">{t("registry.channelAll")}</option>
            <option value="pilot">{t("registry.channelPilot")}</option>
            <option value="stable">{t("registry.channelStable")}</option>
          </select>
        </label>
      </div>
      {error ? (
        <div className="workspace-panel state-panel" role="alert">
          <p className="error-text">{error}</p>
        </div>
      ) : null}
      {loading ? (
        <div className="workspace-panel state-panel" aria-busy="true">
          <p className="muted">{t("registry.loading")}</p>
        </div>
      ) : null}
      {!loading && !error && visibleItems.length === 0 ? (
        <div className="workspace-panel state-panel">
          <h2>{t("registry.emptyTitle")}</h2>
          <p className="muted">{t("registry.emptyDescription")}</p>
        </div>
      ) : null}
      {visibleItems.length > 0 ? (
        <div className="workspace-panel table-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">{t("registry.resultsEyebrow")}</p>
              <h2>{t("registry.workflowVersions")}</h2>
            </div>
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("registry.colSlug")}</th>
                <th>{t("registry.colName")}</th>
                <th>{t("registry.colVersion")}</th>
                <th>{t("registry.colChannel")}</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.flatMap((item) =>
                item.versions.map((version) => (
                  <tr key={version.id}>
                    <td>
                      <a href={`/registry/${item.slug}`}>{item.slug}</a>
                    </td>
                    <td>{item.name}</td>
                    <td>{version.version}</td>
                    <td>
                      <StatusBadge label={version.channel} />
                    </td>
                  </tr>
                )),
              )}
            </tbody>
          </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
