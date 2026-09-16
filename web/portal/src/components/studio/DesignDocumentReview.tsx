"use client";

import type { DesignDocuments } from "@/components/studio/StructuredDesignEditors";
import { useTranslations } from "@/i18n/I18nProvider";
import { isJsonDocument, type JsonDocument } from "@/lib/designForms";

import styles from "./DesignDocumentReview.module.css";

type DocumentType = keyof DesignDocuments;

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function records(value: unknown): JsonDocument[] {
  return Array.isArray(value) ? value.filter(isJsonDocument) : [];
}

function Chips({ values }: { values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <div className={styles.chips}>
      {values.map((value, index) => (
        <span className={styles.chip} key={`${value}-${index}`}>
          {value}
        </span>
      ))}
    </div>
  );
}

function TextList({ title, values }: { title: string; values: string[] }) {
  if (values.length === 0) {
    return null;
  }
  return (
    <section className={styles.group}>
      <h3>{title}</h3>
      <ul className={styles.list}>
        {values.map((value, index) => (
          <li key={`${value}-${index}`}>{value}</li>
        ))}
      </ul>
    </section>
  );
}

function ProfileReview({ document }: { document: JsonDocument }) {
  const t = useTranslations();
  const facts = records(document.facts);
  const pains = records(document.pains);
  const stages = records(document.sdlc);
  const systems = records(document.systems);
  const glossary = isJsonDocument(document.glossary)
    ? Object.entries(document.glossary)
    : [];
  const issueTracker = isJsonDocument(document.issue_tracker)
    ? document.issue_tracker
    : null;
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">{t("documentReview.profileEyebrow")}</p>
          <h2>{t("documentReview.profileHeading")}</h2>
        </div>
        <span className={styles.identifier}>{text(document.customer_id)}</span>
      </header>
      <div className={styles.body}>
        <p className={styles.lead}>{text(document.name)}</p>
        <TextList title={t("documentReview.roles")} values={strings(document.roles)} />
        {glossary.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.glossary")}</h3>
            <dl className={styles.facts}>
              {glossary.map(([term, definition]) => (
                <div key={term}>
                  <dt>{term}</dt>
                  <dd>{text(definition)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}
        {stages.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.sdlc")}</h3>
            <div className={styles.cards}>
              {stages.map((stage, index) => (
                <article className={styles.card} key={`${text(stage.stage)}-${index}`}>
                  <h4>{text(stage.stage) || t("documentReview.stageFallback", { n: index + 1 })}</h4>
                  <p><strong>{t("documentReview.current")}</strong> · {text(stage.current)}</p>
                  <p><strong>{t("documentReview.desired")}</strong> · {text(stage.desired)}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {pains.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.pains")}</h3>
            <div className={styles.cards}>
              {pains.map((pain, index) => (
                <article className={styles.card} key={`${text(pain.description)}-${index}`}>
                  <h4>{text(pain.description)}</h4>
                  <p>{text(pain.impact)}</p>
                  <p className={styles.meta}>{text(pain.frequency)}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null}
        <TextList title={t("documentReview.successCriteria")} values={strings(document.success_criteria)} />
        <TextList title={t("documentReview.constraints")} values={strings(document.constraints)} />
        {facts.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.facts")}</h3>
            <div className={styles.cards}>
              {facts.map((fact, index) => (
                <article className={styles.card} key={`${text(fact.id)}-${index}`}>
                  <h4>{text(fact.statement)}</h4>
                  <p className={styles.meta}>{text(fact.evidence)}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null}
        <TextList title={t("documentReview.assumptions")} values={strings(document.assumptions)} />
        <TextList title={t("documentReview.unknowns")} values={strings(document.unknowns)} />
        {issueTracker ? (
          <section className={styles.group}>
            <h3>{t("documentReview.issueTracker")}</h3>
            <dl className={styles.facts}>
              <div><dt>{t("documentReview.provider")}</dt><dd>{text(issueTracker.provider)}</dd></div>
              <div><dt>{t("documentReview.project")}</dt><dd>{text(issueTracker.project) || text(issueTracker.path)}</dd></div>
              <div><dt>{t("documentReview.connection")}</dt><dd>{text(issueTracker.connection)} · {text(issueTracker.mcp) || text(issueTracker.skill)}</dd></div>
            </dl>
            <Chips values={strings(issueTracker.capabilities)} />
          </section>
        ) : null}
        {systems.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.systems")}</h3>
            <div className={styles.cards}>
              {systems.map((system, index) => (
                <article className={styles.card} key={`${text(system.id)}-${index}`}>
                  <h4>{text(system.id)}</h4>
                  <p>{text(system.kind)} · {text(system.tool)}</p>
                  <Chips values={strings(system.capabilities)} />
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </section>
  );
}

function WorkflowReview({ document }: { document: JsonDocument }) {
  const t = useTranslations();
  const steps = records(document.steps);
  const traceability = records(document.traceability);
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">{t("documentReview.workflowEyebrow")}</p>
          <h2>{text(document.name) || t("documentReview.workflowFallback")}</h2>
        </div>
        <span className={styles.identifier}>{text(document.id)}</span>
      </header>
      <div className={styles.body}>
        <p className={styles.lead}>{text(document.goal)}</p>
        <dl className={styles.facts}>
          <div><dt>{t("documentReview.trigger")}</dt><dd>{text(document.trigger)}</dd></div>
          <div><dt>{t("documentReview.inputs")}</dt><dd>{strings(document.inputs).join(", ")}</dd></div>
          <div><dt>{t("documentReview.outputs")}</dt><dd>{strings(document.outputs).join(", ")}</dd></div>
        </dl>
        <TextList title={t("documentReview.customerRules")} values={strings(document.customer_rules)} />
        {steps.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.steps")}</h3>
            <ol className={styles.stepList}>
              {steps.map((step, index) => {
                const manual = isJsonDocument(step.manual) ? step.manual : null;
                const approval = step.approval === true
                  ? t("documentReview.approvalCombined", { approver: text(step.approver) || t("documentReview.defaultApprover"), timing: text(step.approval_timing) || "before" })
                  : t("documentReview.noApproval");
                const stepId = text(step.id) || t("documentReview.stepFallback", { n: index + 1 });
                return (
                  <li
                    aria-label={t("documentReview.stepReviewAria", { stepId })}
                    className={styles.step}
                    key={`${stepId}-${index}`}
                  >
                    <h4>{text(step.name) || stepId}</h4>
                    <p><strong>{t("documentReview.stepId")}</strong> · {stepId}</p>
                    <p>
                      <strong>{t("documentReview.needs")}</strong> ·{" "}
                      {strings(step.needs).join(", ") || t("documentReview.none")}
                    </p>
                    <p className={styles.meta}>
                      {t("documentReview.stepMeta", { skill: text(step.skill), effect: text(step.effect), approval })}
                    </p>
                    <dl className={styles.facts}>
                      <div><dt>{t("documentReview.tools")}</dt><dd>{strings(step.tools).join(", ") || t("documentReview.none")}</dd></div>
                      <div><dt>{t("documentReview.inputArtifacts")}</dt><dd>{strings(step.inputs).join(", ") || t("documentReview.none")}</dd></div>
                      <div><dt>{t("documentReview.outputArtifacts")}</dt><dd>{strings(step.outputs).join(", ") || t("documentReview.none")}</dd></div>
                    </dl>
                    <p><strong>{t("documentReview.completion")}</strong> · {text(step.completion)}</p>
                    <p><strong>{t("documentReview.onFailure")}</strong> · {text(step.failure)}</p>
                    {manual ? (
                      <div className={styles.warning}>
                        <p><strong>{t("documentReview.manualHandoff", { owner: text(manual.owner) })}</strong></p>
                        <p>{text(manual.instructions)}</p>
                        <p className={styles.meta}>{t("documentReview.resumeCondition", { resumeWhen: text(manual.resume_when) })}</p>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ol>
          </section>
        ) : null}
        {traceability.length > 0 ? (
          <section className={styles.group}>
            <h3>{t("documentReview.traceability")}</h3>
            <div className={styles.cards}>
              {traceability.map((row, index) => (
                <article className={styles.card} key={`${text(row.requirement)}-${index}`}>
                  <h4>{text(row.requirement)}</h4>
                  <Chips values={strings(row.steps)} />
                  <TextList title={t("documentReview.checks")} values={strings(row.checks)} />
                </article>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </section>
  );
}

function ScenariosReview({ document }: { document: JsonDocument }) {
  const t = useTranslations();
  const scenarios = records(document.scenarios);
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">{t("documentReview.scenariosEyebrow")}</p>
          <h2>{t("documentReview.scenariosHeading")}</h2>
        </div>
        <span className={styles.identifier}>{text(document.mode)}</span>
      </header>
      <div className={styles.body}>
        <ol className={styles.stepList}>
          {scenarios.map((scenario, index) => (
            <li className={styles.step} key={`${text(scenario.id)}-${index}`}>
              <h4>{text(scenario.id) || t("documentReview.scenarioFallback", { n: index + 1 })}</h4>
              <p>{text(scenario.given)}</p>
              <p><strong>{t("documentReview.expectedState")}</strong> · {text(scenario.expect)}</p>
              <TextList title={t("documentReview.forbidden")} values={strings(scenario.forbidden)} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function CatalogReview({ document }: { document: JsonDocument }) {
  const t = useTranslations();
  const skills = records(document.skills);
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">{t("documentReview.catalogEyebrow")}</p>
          <h2>{t("documentReview.catalogHeading")}</h2>
        </div>
        <span className={styles.identifier}>{t("documentReview.skillCount", { count: skills.length })}</span>
      </header>
      <div className={styles.body}>
        <div className={styles.cards}>
          {skills.map((skill, index) => {
            const compatibility = isJsonDocument(skill.compatibility)
              ? skill.compatibility
              : {};
            return (
              <article className={styles.card} key={`${text(skill.id)}-${index}`}>
                <h4>{text(skill.id)}</h4>
                <p>{text(skill.description)}</p>
                <p className={styles.meta}>
                  {text(compatibility.runtime)} · {text(compatibility.status)}
                </p>
                <dl className={styles.facts}>
                  <div><dt>{t("documentReview.inputs")}</dt><dd>{strings(skill.inputs).join(", ") || t("documentReview.none")}</dd></div>
                  <div><dt>{t("documentReview.outputs")}</dt><dd>{strings(skill.outputs).join(", ") || t("documentReview.none")}</dd></div>
                  <div><dt>{t("documentReview.effects")}</dt><dd>{strings(skill.effects).join(", ") || t("documentReview.none")}</dd></div>
                </dl>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}

export function DesignDocumentReview({
  documents,
  documentTypes = ["profile", "workflow", "scenarios", "catalog"],
}: {
  documents: DesignDocuments;
  documentTypes?: DocumentType[];
}) {
  return (
    <div className={styles.review}>
      {documentTypes.includes("profile") ? <ProfileReview document={documents.profile} /> : null}
      {documentTypes.includes("workflow") ? <WorkflowReview document={documents.workflow} /> : null}
      {documentTypes.includes("scenarios") ? <ScenariosReview document={documents.scenarios} /> : null}
      {documentTypes.includes("catalog") ? <CatalogReview document={documents.catalog} /> : null}
    </div>
  );
}
