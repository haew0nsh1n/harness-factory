import type { DesignDocuments } from "@/components/studio/StructuredDesignEditors";
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
          <p className="eyebrow">제안 검토 · 고객</p>
          <h2>프로필</h2>
        </div>
        <span className={styles.identifier}>{text(document.customer_id)}</span>
      </header>
      <div className={styles.body}>
        <p className={styles.lead}>{text(document.name)}</p>
        <TextList title="역할" values={strings(document.roles)} />
        {glossary.length > 0 ? (
          <section className={styles.group}>
            <h3>용어</h3>
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
            <h3>SDLC 현재와 목표</h3>
            <div className={styles.cards}>
              {stages.map((stage, index) => (
                <article className={styles.card} key={`${text(stage.stage)}-${index}`}>
                  <h4>{text(stage.stage) || `단계 ${index + 1}`}</h4>
                  <p><strong>현재</strong> · {text(stage.current)}</p>
                  <p><strong>희망</strong> · {text(stage.desired)}</p>
                </article>
              ))}
            </div>
          </section>
        ) : null}
        {pains.length > 0 ? (
          <section className={styles.group}>
            <h3>문제와 영향</h3>
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
        <TextList title="성공 기준" values={strings(document.success_criteria)} />
        <TextList title="제약" values={strings(document.constraints)} />
        {facts.length > 0 ? (
          <section className={styles.group}>
            <h3>확인된 사실</h3>
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
        <TextList title="가정" values={strings(document.assumptions)} />
        <TextList title="미확인 사항" values={strings(document.unknowns)} />
        {issueTracker ? (
          <section className={styles.group}>
            <h3>이슈 트래커</h3>
            <dl className={styles.facts}>
              <div><dt>제공자</dt><dd>{text(issueTracker.provider)}</dd></div>
              <div><dt>프로젝트</dt><dd>{text(issueTracker.project) || text(issueTracker.path)}</dd></div>
              <div><dt>연결</dt><dd>{text(issueTracker.connection)} · {text(issueTracker.mcp) || text(issueTracker.skill)}</dd></div>
            </dl>
            <Chips values={strings(issueTracker.capabilities)} />
          </section>
        ) : null}
        {systems.length > 0 ? (
          <section className={styles.group}>
            <h3>연결 시스템</h3>
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
  const steps = records(document.steps);
  const traceability = records(document.traceability);
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">제안 검토 · 실행</p>
          <h2>{text(document.name) || "워크플로"}</h2>
        </div>
        <span className={styles.identifier}>{text(document.id)}</span>
      </header>
      <div className={styles.body}>
        <p className={styles.lead}>{text(document.goal)}</p>
        <dl className={styles.facts}>
          <div><dt>시작 조건</dt><dd>{text(document.trigger)}</dd></div>
          <div><dt>입력</dt><dd>{strings(document.inputs).join(", ")}</dd></div>
          <div><dt>산출물</dt><dd>{strings(document.outputs).join(", ")}</dd></div>
        </dl>
        <TextList title="고객 규칙" values={strings(document.customer_rules)} />
        {steps.length > 0 ? (
          <section className={styles.group}>
            <h3>실행 단계</h3>
            <ol className={styles.stepList}>
              {steps.map((step, index) => {
                const manual = isJsonDocument(step.manual) ? step.manual : null;
                const approval = step.approval === true
                  ? `${text(step.approver) || "지정 승인자"} · ${text(step.approval_timing) || "before"}`
                  : "추가 승인 없음";
                const stepId = text(step.id) || `단계-${index + 1}`;
                return (
                  <li
                    aria-label={`${stepId} 단계 검토`}
                    className={styles.step}
                    key={`${stepId}-${index}`}
                  >
                    <h4>{text(step.name) || stepId}</h4>
                    <p><strong>단계 ID</strong> · {stepId}</p>
                    <p>
                      <strong>선행 단계</strong> ·{" "}
                      {strings(step.needs).join(", ") || "없음"}
                    </p>
                    <p className={styles.meta}>
                      스킬 {text(step.skill)} · 효과 {text(step.effect)} · 승인 {approval}
                    </p>
                    <dl className={styles.facts}>
                      <div><dt>도구</dt><dd>{strings(step.tools).join(", ") || "없음"}</dd></div>
                      <div><dt>입력 아티팩트</dt><dd>{strings(step.inputs).join(", ") || "없음"}</dd></div>
                      <div><dt>출력 아티팩트</dt><dd>{strings(step.outputs).join(", ") || "없음"}</dd></div>
                    </dl>
                    <p><strong>완료</strong> · {text(step.completion)}</p>
                    <p><strong>실패 시</strong> · {text(step.failure)}</p>
                    {manual ? (
                      <div className={styles.warning}>
                        <p><strong>수동 인계 · {text(manual.owner)}</strong></p>
                        <p>{text(manual.instructions)}</p>
                        <p className={styles.meta}>재개 조건 · {text(manual.resume_when)}</p>
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
            <h3>요구사항 추적</h3>
            <div className={styles.cards}>
              {traceability.map((row, index) => (
                <article className={styles.card} key={`${text(row.requirement)}-${index}`}>
                  <h4>{text(row.requirement)}</h4>
                  <Chips values={strings(row.steps)} />
                  <TextList title="검사" values={strings(row.checks)} />
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
  const scenarios = records(document.scenarios);
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">제안 검토 · 검증</p>
          <h2>시나리오</h2>
        </div>
        <span className={styles.identifier}>{text(document.mode)}</span>
      </header>
      <div className={styles.body}>
        <ol className={styles.stepList}>
          {scenarios.map((scenario, index) => (
            <li className={styles.step} key={`${text(scenario.id)}-${index}`}>
              <h4>{text(scenario.id) || `시나리오 ${index + 1}`}</h4>
              <p>{text(scenario.given)}</p>
              <p><strong>예상 상태</strong> · {text(scenario.expect)}</p>
              <TextList title="금지 동작" values={strings(scenario.forbidden)} />
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function CatalogReview({ document }: { document: JsonDocument }) {
  const skills = records(document.skills);
  return (
    <section className={`workspace-panel ${styles.document}`}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">서버 소유 · 사용 가능 항목</p>
          <h2>승인 카탈로그</h2>
        </div>
        <span className={styles.identifier}>{skills.length}개 스킬</span>
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
                  <div><dt>입력</dt><dd>{strings(skill.inputs).join(", ") || "없음"}</dd></div>
                  <div><dt>출력</dt><dd>{strings(skill.outputs).join(", ") || "없음"}</dd></div>
                  <div><dt>효과</dt><dd>{strings(skill.effects).join(", ") || "없음"}</dd></div>
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
