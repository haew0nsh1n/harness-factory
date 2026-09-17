export type JsonDocument = Record<string, unknown>;

export interface FieldRead<T> {
  value: T | null;
  error?: string;
}

export interface ProfileFormRead {
  values: {
    customerId: string | null;
    name: string | null;
  };
  errors: Partial<Record<"customerId" | "name", string>>;
}

export interface DependencyAnalysis {
  edges: Array<{ from: string; to: string }>;
  missing: Array<{ stepId: string; dependencyId: string }>;
  cycles: string[][];
}

export type DesignFormErrors = Record<string, string>;

const IDENTIFIER = /^[a-z][a-z0-9-]*$/;
const EFFECTS = new Set(["read", "local", "external-write", "manual"]);
const TRACKER_PROVIDERS = new Set(["markdown", "github", "jira"]);
const TRACKER_CONNECTIONS = new Set(["local", "skill", "mcp"]);
const SCENARIO_STATES = new Set([
  "awaiting-answer",
  "awaiting-approval",
  "awaiting-manual",
  "blocked",
  "cancelled",
  "failed",
  "uncertain",
  "completed",
]);

export function isJsonDocument(value: unknown): value is JsonDocument {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function updateDocumentField<T extends Record<string, unknown>>(
  document: T,
  field: string,
  value: unknown,
): T {
  return { ...document, [field]: value };
}

function readString(
  document: JsonDocument,
  field: string,
  label: string,
): FieldRead<string> {
  const value = document[field];
  if (typeof value === "string") {
    return { value };
  }
  return {
    value: null,
    error: `${label} 값은 문자열이어야 합니다. 현재 값은 변경하지 않았습니다.`,
  };
}

export function readProfileForm(document: JsonDocument): ProfileFormRead {
  const customerId = readString(document, "customer_id", "고객 ID");
  const name = readString(document, "name", "고객 이름");
  return {
    values: {
      customerId: customerId.value,
      name: name.value,
    },
    errors: {
      customerId: customerId.error,
      name: name.error,
    },
  };
}

export function updateProfileName<T extends JsonDocument>(
  document: T,
  name: string,
): T {
  return updateDocumentField(document, "name", name);
}

function workflowSteps(document: JsonDocument): JsonDocument[] {
  const steps = document.steps;
  if (!Array.isArray(steps)) {
    return [];
  }
  return steps.filter(isJsonDocument);
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function analyzeDependencies(document: JsonDocument): DependencyAnalysis {
  const steps = workflowSteps(document);
  const ids = new Set(
    steps
      .map((step) => step.id)
      .filter((id): id is string => typeof id === "string"),
  );
  const edges: DependencyAnalysis["edges"] = [];
  const missing: DependencyAnalysis["missing"] = [];
  const adjacency = new Map<string, string[]>();

  for (const step of steps) {
    if (typeof step.id !== "string") {
      continue;
    }
    const dependencies = stringArray(step.needs);
    adjacency.set(
      step.id,
      dependencies.filter((dependency) => ids.has(dependency)),
    );
    for (const dependency of dependencies) {
      edges.push({ from: dependency, to: step.id });
      if (!ids.has(dependency)) {
        missing.push({ stepId: step.id, dependencyId: dependency });
      }
    }
  }

  const cycles: string[][] = [];
  const visiting = new Set<string>();
  const visited = new Set<string>();

  function visit(id: string, path: string[]): void {
    if (visiting.has(id)) {
      const start = path.indexOf(id);
      cycles.push([...path.slice(start), id]);
      return;
    }
    if (visited.has(id)) {
      return;
    }
    visiting.add(id);
    for (const dependency of adjacency.get(id) ?? []) {
      visit(dependency, [...path, id]);
    }
    visiting.delete(id);
    visited.add(id);
  }

  for (const id of ids) {
    visit(id, []);
  }

  return { edges, missing, cycles };
}

export function parseJsonField(
  text: string,
  label: string,
): { value?: unknown; error?: string } {
  try {
    return { value: JSON.parse(text) };
  } catch (cause) {
    const detail = cause instanceof Error ? cause.message : "알 수 없는 구문 오류";
    return { error: `${label} JSON이 올바르지 않습니다: ${detail}` };
  }
}

function requireString(
  errors: DesignFormErrors,
  path: string,
  value: unknown,
  identifier = false,
): void {
  if (typeof value !== "string") {
    errors[path] = "현재 값은 문자열이어야 합니다. 고급 JSON의 원본 값은 유지됩니다.";
  } else if (!value.trim()) {
    errors[path] = "값을 입력하세요.";
  } else if (identifier && !IDENTIFIER.test(value)) {
    errors[path] = "소문자 하이픈 식별자 형식이어야 합니다.";
  }
}

function requireStringList(
  errors: DesignFormErrors,
  path: string,
  value: unknown,
  nonempty = false,
): string[] {
  if (!Array.isArray(value)) {
    errors[path] = "현재 값은 문자열 목록이어야 합니다. 고급 JSON의 원본 값은 유지됩니다.";
    return [];
  }
  if (nonempty && value.length === 0) {
    errors[path] = "하나 이상의 항목이 필요합니다.";
  }
  value.forEach((item, index) => {
    requireString(errors, `${path}.${index}`, item);
    if (typeof item !== "string") {
      errors[path] = "모든 항목은 문자열이어야 합니다. 원본 값은 유지됩니다.";
    }
  });
  return value.filter((item): item is string => typeof item === "string");
}

function requireObjectList(
  errors: DesignFormErrors,
  path: string,
  value: unknown,
  nonempty = false,
): JsonDocument[] {
  if (!Array.isArray(value) || value.some((item) => !isJsonDocument(item))) {
    errors[path] = "현재 값은 객체 목록이어야 합니다. 고급 JSON의 원본 값은 유지됩니다.";
    return [];
  }
  if (nonempty && value.length === 0) {
    errors[path] = "하나 이상의 항목이 필요합니다.";
  }
  return value as JsonDocument[];
}

function validateProfile(document: JsonDocument, errors: DesignFormErrors): void {
  if (document.schema_version !== 1) {
    errors["profile.schema_version"] = "schema_version은 1이어야 합니다.";
  }
  requireString(errors, "profile.customer_id", document.customer_id, true);
  requireString(errors, "profile.name", document.name);
  requireObjectList(errors, "profile.sdlc", document.sdlc, true).forEach((row, index) => {
    requireString(errors, `profile.sdlc.${index}.stage`, row.stage);
    requireString(errors, `profile.sdlc.${index}.current`, row.current);
    requireString(errors, `profile.sdlc.${index}.desired`, row.desired);
  });
  if (!isJsonDocument(document.glossary)) {
    errors["profile.glossary"] = "현재 값은 용어와 정의의 객체여야 합니다.";
  } else {
    Object.entries(document.glossary).forEach(([term, definition], index) => {
      if (!term.trim()) {
        errors[`profile.glossary.${index}.term`] = "용어를 입력하세요.";
      }
      requireString(errors, `profile.glossary.${term}`, definition);
    });
  }
  requireStringList(errors, "profile.roles", document.roles, true);
  requireObjectList(errors, "profile.pains", document.pains).forEach((row, index) => {
    requireString(errors, `profile.pains.${index}.description`, row.description);
    requireString(errors, `profile.pains.${index}.impact`, row.impact);
    requireString(errors, `profile.pains.${index}.frequency`, row.frequency);
  });
  requireStringList(errors, "profile.success_criteria", document.success_criteria, true);
  requireStringList(errors, "profile.constraints", document.constraints);
  requireObjectList(errors, "profile.facts", document.facts).forEach((row, index) => {
    requireString(errors, `profile.facts.${index}.id`, row.id, true);
    requireString(errors, `profile.facts.${index}.statement`, row.statement);
    requireString(errors, `profile.facts.${index}.evidence`, row.evidence);
  });
  requireStringList(errors, "profile.assumptions", document.assumptions);
  requireStringList(errors, "profile.unknowns", document.unknowns);
  requireObjectList(errors, "profile.systems", document.systems).forEach((row, index) => {
    requireString(errors, `profile.systems.${index}.id`, row.id, true);
    requireString(errors, `profile.systems.${index}.kind`, row.kind);
    requireString(errors, `profile.systems.${index}.tool`, row.tool);
    requireStringList(errors, `profile.systems.${index}.capabilities`, row.capabilities, true);
  });
  if (!isJsonDocument(document.issue_tracker)) {
    errors["profile.issue_tracker"] = "현재 값은 이슈 트래커 객체여야 합니다.";
    return;
  }
  const tracker = document.issue_tracker;
  requireString(errors, "profile.issue_tracker.system_id", tracker.system_id, true);
  requireString(errors, "profile.issue_tracker.project", tracker.project);
  if (typeof tracker.provider !== "string" || !TRACKER_PROVIDERS.has(tracker.provider)) {
    errors["profile.issue_tracker.provider"] = "markdown, github, jira 중 하나를 선택하세요.";
  } else if (typeof tracker.project === "string") {
    const projectPattern =
      tracker.provider === "github"
        ? /^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?\/[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$/
        : tracker.provider === "jira"
          ? /^[A-Z][A-Z0-9_-]*$/
          : /^[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?$/;
    if (!projectPattern.test(tracker.project)) {
      errors["profile.issue_tracker.project"] = "선택한 제공자에 맞는 프로젝트 식별자를 입력하세요.";
    }
  }
  if (typeof tracker.connection !== "string" || !TRACKER_CONNECTIONS.has(tracker.connection)) {
    errors["profile.issue_tracker.connection"] = "local, skill, mcp 중 하나를 선택하세요.";
  }
  requireStringList(errors, "profile.issue_tracker.capabilities", tracker.capabilities, true);
  if (tracker.provider === "markdown") {
    requireString(errors, "profile.issue_tracker.path", tracker.path);
    if (tracker.connection !== "local") {
      errors["profile.issue_tracker.connection"] = "Git+Markdown은 local 연결을 사용해야 합니다.";
    }
  } else if (tracker.connection === "local") {
    errors["profile.issue_tracker.connection"] = "GitHub Issues와 Jira는 skill 또는 mcp 연결이 필요합니다.";
  }
  if (tracker.connection === "skill") {
    requireString(errors, "profile.issue_tracker.skill", tracker.skill, true);
  }
  if (tracker.connection === "mcp") {
    requireString(errors, "profile.issue_tracker.mcp", tracker.mcp);
  }
}

function validateWorkflow(
  document: JsonDocument,
  errors: DesignFormErrors,
  catalog: JsonDocument | null,
): void {
  const approvedSkills = new Set(
    requireObjectList({}, "catalog.skills", catalog?.skills).flatMap((skill) =>
      typeof skill.id === "string" ? [skill.id] : [],
    ),
  );
  if (document.schema_version !== 1) {
    errors["workflow.schema_version"] = "schema_version은 1이어야 합니다.";
  }
  for (const field of ["id", "customer_id"] as const) {
    requireString(errors, `workflow.${field}`, document[field], true);
  }
  for (const field of ["name", "goal", "trigger"] as const) {
    requireString(errors, `workflow.${field}`, document[field]);
  }
  requireStringList(errors, "workflow.inputs", document.inputs, true);
  requireStringList(errors, "workflow.outputs", document.outputs, true);
  requireStringList(errors, "workflow.customer_rules", document.customer_rules);
  requireObjectList(errors, "workflow.steps", document.steps, true).forEach((step, index) => {
    const path = `workflow.steps.${index}`;
    requireString(errors, `${path}.id`, step.id, true);
    requireString(errors, `${path}.name`, step.name);
    requireString(errors, `${path}.skill`, step.skill, true);
    if (
      typeof step.skill === "string" &&
      approvedSkills.size > 0 &&
      !approvedSkills.has(step.skill)
    ) {
      errors[`${path}.skill`] = "서버 승인 카탈로그의 스킬을 선택하세요.";
    }
    requireStringList(errors, `${path}.needs`, step.needs);
    requireStringList(errors, `${path}.inputs`, step.inputs);
    requireStringList(errors, `${path}.outputs`, step.outputs);
    requireStringList(errors, `${path}.tools`, step.tools);
    if (typeof step.effect !== "string" || !EFFECTS.has(step.effect)) {
      errors[`${path}.effect`] = "허용된 효과를 선택하세요.";
    }
    if (typeof step.approval !== "boolean") {
      errors[`${path}.approval`] = "승인 필요 여부는 참/거짓이어야 합니다.";
    }
    if (
      step.approval_timing !== undefined &&
      step.approval_timing !== "before" &&
      step.approval_timing !== "after"
    ) {
      errors[`${path}.approval_timing`] = "before 또는 after를 선택하세요.";
    }
    if (step.approval === true) {
      requireString(errors, `${path}.approver`, step.approver);
    } else if (step.approver !== null && typeof step.approver !== "string") {
      errors[`${path}.approver`] = "승인 역할은 문자열 또는 null이어야 합니다.";
    }
    requireString(errors, `${path}.completion`, step.completion);
    requireString(errors, `${path}.failure`, step.failure);
    if (step.manual !== null) {
      if (!isJsonDocument(step.manual)) {
        errors[`${path}.manual`] = "수동 인계는 객체 또는 null이어야 합니다.";
      } else {
        requireString(errors, `${path}.manual.owner`, step.manual.owner);
        requireString(errors, `${path}.manual.instructions`, step.manual.instructions);
        requireString(errors, `${path}.manual.resume_when`, step.manual.resume_when);
      }
    }
  });
  requireObjectList(errors, "workflow.traceability", document.traceability).forEach((row, index) => {
    const path = `workflow.traceability.${index}`;
    requireString(errors, `${path}.requirement`, row.requirement);
    requireStringList(errors, `${path}.steps`, row.steps);
    requireStringList(errors, `${path}.checks`, row.checks);
  });
}

function validateScenarios(document: JsonDocument, errors: DesignFormErrors): void {
  if (document.schema_version !== 1) {
    errors["scenarios.schema_version"] = "schema_version은 1이어야 합니다.";
  }
  requireString(errors, "scenarios.workflow", document.workflow, true);
  if (document.mode !== "read-only-agent-simulation") {
    errors["scenarios.mode"] = "read-only-agent-simulation 모드만 허용됩니다.";
  }
  requireObjectList(errors, "scenarios.scenarios", document.scenarios, true).forEach((scenario, index) => {
    const path = `scenarios.scenarios.${index}`;
    requireString(errors, `${path}.id`, scenario.id, true);
    requireString(errors, `${path}.given`, scenario.given);
    if (typeof scenario.expect !== "string" || !SCENARIO_STATES.has(scenario.expect)) {
      errors[`${path}.expect`] = "허용된 예상 상태를 선택하세요.";
    }
    requireStringList(errors, `${path}.forbidden`, scenario.forbidden);
  });
}

export function validateDesignFormDocuments(documents: {
  profile: JsonDocument;
  workflow: JsonDocument;
  scenarios: JsonDocument;
  catalog?: JsonDocument;
}, catalog: JsonDocument | null = documents.catalog ?? null, _t?: unknown): DesignFormErrors {
  const errors: DesignFormErrors = {};
  validateProfile(documents.profile, errors);
  validateWorkflow(documents.workflow, errors, catalog);
  validateScenarios(documents.scenarios, errors);
  return errors;
}
