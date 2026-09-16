"use client";

import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/StatusBadge";
import { useLocale, useTranslations } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import type {
  DesignStatus,
  HarnessDesign,
  InterviewSession,
} from "@/lib/types";

function recommendedActionKey(status: DesignStatus): string {
  switch (status) {
    case "draft":
      return "studio.action.draft";
    case "validated":
      return "studio.action.validated";
    case "approved":
    case "build-queued":
    case "failed":
      return "studio.action.build";
    case "built":
      return "studio.action.built";
    default:
      return "studio.action.default";
  }
}

function formatTimestamp(value: string, locale: string): string {
  return new Date(value).toLocaleString(locale === "ko" ? "ko-KR" : "en-US");
}

export function StudioPageContent() {
  const t = useTranslations();
  const locale = useLocale();
  const [designs, setDesigns] = useState<HarnessDesign[]>([]);
  const [interviews, setInterviews] = useState<InterviewSession[]>([]);
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
        if (process.env.NODE_ENV !== "test") {
          try {
            const interviewItems =
              await api<InterviewSession[]>("/interviews");
            if (active) {
              setInterviews(interviewItems);
            }
          } catch (cause) {
            if (active) {
              setError(
                cause instanceof ApiError
                  ? cause.message
                  : t("studio.interviewLoadError"),
              );
            }
          }
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : t("studio.designLoadError"));
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
  }, []);

  const visibleDesigns = designs.filter((design) => design.language === locale);

  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">{t("studio.eyebrow")}</p>
        <h1 className="workspace-heading">{t("studio.heading")}</h1>
        <p className="page-description">{t("studio.description")}</p>
        <div className="actions-row">
          <a className="button-primary" href="/studio/interviews/new">
            {t("studio.newInterview")}
          </a>
        </div>
      </header>
      {error ? (
        <div className="workspace-panel state-panel" role="alert">
          <p className="error-text">{error}</p>
        </div>
      ) : null}
      {loading ? (
        <div className="workspace-panel state-panel" aria-busy="true">
          <p className="muted">{t("studio.loadingDesigns")}</p>
        </div>
      ) : null}
      {!loading && !error && visibleDesigns.length === 0 ? (
        <div className="workspace-panel state-panel">
          <h2>{t("studio.emptyTitle")}</h2>
          <p className="muted">{t("studio.emptyDescription")}</p>
        </div>
      ) : null}
      {!loading && !error ? (
        <section className="workspace-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">{t("studio.retention")}</p>
              <h2>{t("studio.inProgressInterviews")}</h2>
            </div>
            <p className="record-count">
              {interviews.length}
              {t("common.countUnit")}
            </p>
          </div>
          {interviews.length === 0 ? (
            <p className="muted">{t("studio.noResumable")}</p>
          ) : (
            <div className="resume-list">
              {interviews.map((interview) => (
                <a
                  className="resume-card"
                  href={`/studio/interviews/${interview.id}`}
                  key={interview.id}
                >
                  <strong>{interview.name}</strong>
                  <span>
                    {t("studio.stageRevision", {
                      stage: interview.stage,
                      revision: interview.revision,
                    })}
                  </span>
                  <span>
                    {t("studio.expiresAt", {
                      time: formatTimestamp(interview.expires_at, locale),
                    })}
                  </span>
                </a>
              ))}
            </div>
          )}
        </section>
      ) : null}
      {visibleDesigns.length > 0 ? (
        <div className="workspace-panel table-panel">
          <div className="section-header">
            <div>
              <p className="eyebrow">{t("studio.savedDesigns")}</p>
              <h2>{t("studio.designList")}</h2>
            </div>
            <p className="record-count">
              {visibleDesigns.length}
              {t("common.countUnit")}
            </p>
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("studio.colName")}</th>
                <th>{t("studio.colCustomer")}</th>
                <th>{t("studio.colRevision")}</th>
                <th>{t("studio.colStatus")}</th>
                <th>{t("studio.colUpdated")}</th>
                <th>{t("studio.colNextAction")}</th>
              </tr>
            </thead>
            <tbody>
              {visibleDesigns.map((design) => (
                <tr key={design.id}>
                  <td>
                    <a href={`/studio/${design.id}`}>{design.name}</a>
                  </td>
                  <td>{design.customer_id}</td>
                  <td>{design.revision}</td>
                  <td>
                    <StatusBadge label={design.status} />
                  </td>
                  <td>{formatTimestamp(design.updated_at, locale)}</td>
                  <td>{t(recommendedActionKey(design.status))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
