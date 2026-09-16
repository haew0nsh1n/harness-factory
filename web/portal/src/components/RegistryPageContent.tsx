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
            cause instanceof ApiError
              ? cause.message
              : "레지스트리 자산을 불러오지 못했습니다.",
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
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">Asset Registry</p>
        <h1 className="workspace-heading">게시된 워크플로 레지스트리</h1>
        <p className="page-description">
          게시 상태가 확인된 버전만 검색하고 변경 불가 매니페스트를 검토합니다.
        </p>
      </header>
      <div className="workspace-panel filter-panel">
        <label className="field">
          <span>자산 검색</span>
          <input
            type="search"
            aria-label="자산 검색"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="슬러그 또는 이름 검색"
          />
        </label>
        <label className="field">
          <span>배포 채널</span>
          <select
            aria-label="배포 채널"
            value={channel}
            onChange={(event) =>
              setChannel(event.target.value as "" | "pilot" | "stable")
            }
          >
            <option value="">게시된 모든 채널</option>
            <option value="pilot">파일럿</option>
            <option value="stable">안정</option>
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
          <p className="muted">레지스트리를 불러오는 중입니다.</p>
        </div>
      ) : null}
      {!loading && !error && visibleItems.length === 0 ? (
        <div className="workspace-panel state-panel">
          <h2>게시된 워크플로가 없습니다.</h2>
          <p className="muted">검색어 또는 채널 필터를 변경해 보세요.</p>
        </div>
      ) : null}
      {visibleItems.length > 0 ? (
        <div className="workspace-panel table-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">게시 결과</p>
              <h2>워크플로 버전</h2>
            </div>
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>슬러그</th>
                <th>이름</th>
                <th>버전</th>
                <th>채널</th>
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
