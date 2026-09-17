"use client";

import { useLocale, useTranslations } from "@/i18n/I18nProvider";

const STEPS = [
  "interview",
  "design",
  "review",
  "build",
  "registry",
  "install",
] as const;

const CONCEPTS = ["spec", "context", "execution", "verify"] as const;

const SKILLS = [
  { key: "clarify", io: "issue → brief", repo: "mattpocock/skills", url: "https://github.com/mattpocock/skills", license: "MIT" },
  { key: "plan", io: "brief → plan", repo: "obra/superpowers", url: "https://github.com/obra/superpowers", license: "MIT" },
  { key: "tdd", io: "plan → implementation·test-results", repo: "obra/superpowers", url: "https://github.com/obra/superpowers", license: "MIT" },
  { key: "review", io: "implementation·test-results → review-report", repo: "garrytan/gstack", url: "https://github.com/garrytan/gstack", license: "MIT" },
  { key: "manual", io: "review-report → pr-url", repo: "mattpocock/skills", url: "https://github.com/mattpocock/skills", license: "MIT" },
  { key: "issues", io: "issue-request → issue-file", repo: "mattpocock/skills", url: "https://github.com/mattpocock/skills", license: "MIT" },
] as const;

export function HelpPageContent() {
  const t = useTranslations();
  const locale = useLocale();
  return (
    <div className="page-stack">
      <header className="page-intro">
        <p className="eyebrow">{t("help.eyebrow")}</p>
        <h1 className="workspace-heading">{t("help.heading")}</h1>
        <p className="page-description">{t("help.intro")}</p>
        <p className="page-description help-philosophy">{t("help.philosophy")}</p>
      </header>
      <section className="workspace-panel help-overview">
        <img
          className="help-overview-image"
          src={`/help/overview-${locale}.png`}
          alt={t("help.overviewAlt")}
        />
        <p className="page-description">{t("help.flowIntro")}</p>
        <ol className="help-flow" aria-label={t("help.flowAria")}>
          {STEPS.map((step, index) => (
            <li className="help-flow-step" key={step}>
              <span className="help-flow-index">{index + 1}</span>
              <span className="help-flow-label">
                {t(`help.steps.${step}.label`)}
              </span>
              <span className="help-flow-desc">
                {t(`help.steps.${step}.desc`)}
              </span>
            </li>
          ))}
        </ol>
        <p className="muted help-role-note">{t("help.roleNote")}</p>
        <h2 className="help-subheading">{t("help.roles.heading")}</h2>
        <ul className="help-role-list">
          <li>{t("help.roles.author")}</li>
          <li>{t("help.roles.reviewer")}</li>
          <li>{t("help.roles.registryAdmin")}</li>
        </ul>
      </section>
      <section className="workspace-panel">
        <p className="eyebrow">{t("help.concept.eyebrow")}</p>
        <h2>{t("help.concept.heading")}</h2>
        <p className="page-description">{t("help.concept.intro")}</p>
        <div className="help-concept-grid">
          {CONCEPTS.map((concept) => (
            <div className="help-concept-card" key={concept}>
              <h3>{t(`help.concept.${concept}.label`)}</h3>
              <p>{t(`help.concept.${concept}.desc`)}</p>
            </div>
          ))}
        </div>
        <p className="muted help-concept-note">{t("help.concept.note")}</p>
      </section>
      <section className="workspace-panel">
        <p className="eyebrow">{t("help.skillsSection.eyebrow")}</p>
        <h2>{t("help.skillsSection.heading")}</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>{t("help.skillsSection.colName")}</th>
                <th>{t("help.skillsSection.colDesc")}</th>
                <th>{t("help.skillsSection.colIo")}</th>
                <th>{t("help.skillsSection.colSource")}</th>
                <th>{t("help.skillsSection.colLicense")}</th>
              </tr>
            </thead>
            <tbody>
              {SKILLS.map((skill) => (
                <tr key={skill.key}>
                  <td>
                    <code>{t(`help.skillItems.${skill.key}.name`)}</code>
                  </td>
                  <td>{t(`help.skillItems.${skill.key}.desc`)}</td>
                  <td>
                    <code>{skill.io}</code>
                  </td>
                  <td>
                    <a href={skill.url} target="_blank" rel="noreferrer">
                      {skill.repo}
                    </a>
                  </td>
                  <td>{skill.license}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">{t("help.skillsSection.note")}</p>
      </section>
    </div>
  );
}
