"use client";

import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { api, ApiError } from "@/lib/api";
import type { DesignStatus, HarnessDesign } from "@/lib/types";

function recommendedAction(status: DesignStatus): string {
  switch (status) {
    case "draft":
      return "Validate draft";
    case "validated":
      return "Review digest";
    case "approved":
    case "build-queued":
    case "failed":
      return "Queue build";
    case "built":
      return "Built artifact";
    default:
      return "Review";
  }
}

function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}

export function StudioPageContent() {
  const [designs, setDesigns] = useState<HarnessDesign[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function load(): Promise<void> {
      try {
        const items = await api<HarnessDesign[]>("/designs");
        if (active) {
          setDesigns(items);
          setError(null);
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : "Unable to load designs.");
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
  }, []);

  return (
    <div>
      <div className="page-header">
        <h1>Harness Studio</h1>
        <a href="/">Back to dashboard</a>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {loading ? <p className="muted">Loading designs…</p> : null}
      {!loading && designs.length === 0 ? <p className="muted">No designs yet.</p> : null}
      {designs.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Customer ID</th>
                <th>Revision</th>
                <th>Status</th>
                <th>Updated</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {designs.map((design) => (
                <tr key={design.id}>
                  <td>
                    <a href={`/studio/${design.id}`}>{design.name}</a>
                  </td>
                  <td>{design.customer_id}</td>
                  <td>{design.revision}</td>
                  <td>
                    <StatusBadge label={design.status} />
                  </td>
                  <td>{formatTimestamp(design.updated_at)}</td>
                  <td>{recommendedAction(design.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
