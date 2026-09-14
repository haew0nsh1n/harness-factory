"use client";

import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
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
            cause instanceof ApiError ? cause.message : "Unable to load registry assets.",
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
  }, [channel, query]);

  const visibleItems = useMemo(
    () =>
      items
        .map((item) => ({ ...item, versions: onlyPublishedVersions(item) }))
        .filter((item) => item.versions.length > 0),
    [items],
  );

  return (
    <div>
      <div className="page-header">
        <h1>Asset Registry</h1>
        <a href="/">Back to dashboard</a>
      </div>
      <div className="form-grid">
        <label className="field">
          <span>Search assets</span>
          <input
            aria-label="Search assets"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search slug or name"
          />
        </label>
        <label className="field">
          <span>Channel</span>
          <select
            aria-label="Channel"
            value={channel}
            onChange={(event) =>
              setChannel(event.target.value as "" | "pilot" | "stable")
            }
          >
            <option value="">All published channels</option>
            <option value="pilot">Pilot</option>
            <option value="stable">Stable</option>
          </select>
        </label>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {loading ? <p className="muted">Loading registry…</p> : null}
      {!loading && visibleItems.length === 0 ? (
        <p className="muted">No published assets yet.</p>
      ) : null}
      {visibleItems.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Slug</th>
                <th>Name</th>
                <th>Version</th>
                <th>Channel</th>
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
      ) : null}
    </div>
  );
}
