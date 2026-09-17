"use client";

import { useMemo, useState } from "react";

import { objectRows } from "@/components/studio/DesignFormFields";
import { useLocale, useTranslations } from "@/i18n/I18nProvider";
import { scenarioLabel } from "@/i18n/scenarioLabels";
import { analyzeDependencies, type JsonDocument } from "@/lib/designForms";

interface FlowStep {
  id: string;
  name: string;
  skill: string;
  effect: string;
  needs: string[];
  tools: string[];
  approval: boolean;
  manual: boolean;
  rank: number;
  index: number;
}

interface FlowScenario {
  id: string;
  given: string;
  expect: string;
  forbidden: string[];
}

type TraceState = "run" | "stop" | "pending";

interface TraceEntry {
  step: FlowStep;
  state: TraceState;
  violation: boolean;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function short(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

const NODE_W = 158;
const NODE_H = 60;
const COL_GAP = 76;
const ROW_GAP_V = 66;
const CANVAS_PAD = 16;

const SCENARIO_STATE_ORDER = [
  "completed",
  "awaiting-approval",
  "awaiting-manual",
  "awaiting-answer",
  "blocked",
  "failed",
  "cancelled",
  "uncertain",
];

function readSteps(workflow: JsonDocument | null): FlowStep[] {
  if (!workflow) {
    return [];
  }
  const rows = objectRows(workflow.steps);
  const raw = rows.map(({ value }, index) => ({
    id: text(value.id) || `step-${index + 1}`,
    name: text(value.name),
    skill: text(value.skill),
    effect: text(value.effect) || "read",
    needs: strings(value.needs),
    tools: strings(value.tools),
    approval: value.approval === true,
    manual: value.manual !== null && value.manual !== undefined,
    index,
  }));

  const ids = new Set(raw.map((step) => step.id));
  const rank = new Map<string, number>();
  const compute = (id: string, stack: Set<string>): number => {
    const cached = rank.get(id);
    if (cached !== undefined) {
      return cached;
    }
    if (stack.has(id)) {
      return 0;
    }
    stack.add(id);
    const step = raw.find((entry) => entry.id === id);
    const deps = (step?.needs ?? []).filter((dep) => ids.has(dep));
    const value =
      deps.length === 0 ? 0 : Math.max(...deps.map((dep) => compute(dep, stack) + 1));
    stack.delete(id);
    rank.set(id, value);
    return value;
  };

  return raw
    .map((step) => ({ ...step, rank: compute(step.id, new Set<string>()) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index);
}

interface GraphNode {
  id: string;
  kind: "orchestrator" | "step" | "artifact";
  label: string;
  sub: string;
  effect: string;
  approval: boolean;
  manual: boolean;
  color: string;
}

interface GraphEdge {
  from: string;
  to: string;
  label: string;
}

interface WorkflowStep {
  id: string;
  name: string;
  skill: string;
  effect: string;
  approval: boolean;
  manual: boolean;
  inputs: string[];
  outputs: string[];
}

const SKILL_PALETTE = [
  "#7a5bd0",
  "#2563eb",
  "#d97706",
  "#16a34a",
  "#0891b2",
  "#db2777",
  "#65a30d",
  "#dc2626",
];

const ORCHESTRATOR_ID = "__orchestrator";

function skillColor(skill: string, skills: string[]): string {
  const index = skills.indexOf(skill);
  return index >= 0 ? SKILL_PALETTE[index % SKILL_PALETTE.length] : "#64748b";
}

function readWorkflowSteps(workflow: JsonDocument | null): WorkflowStep[] {
  if (!workflow) {
    return [];
  }
  return objectRows(workflow.steps).map(({ value }, index) => ({
    id: text(value.id) || `step-${index + 1}`,
    name: text(value.name),
    skill: text(value.skill),
    effect: text(value.effect) || "read",
    approval: value.approval === true,
    manual: value.manual !== null && value.manual !== undefined,
    inputs: strings(value.inputs),
    outputs: strings(value.outputs),
  }));
}

function buildFlow(
  workflow: JsonDocument | null,
  showArtifacts: boolean,
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const wfSteps = readWorkflowSteps(workflow);
  if (wfSteps.length === 0) {
    return { nodes: [], edges: [] };
  }
  const skills = [...new Set(wfSteps.map((step) => step.skill).filter(Boolean))];
  const producedBy = new Map<string, string[]>();
  for (const step of wfSteps) {
    for (const artifact of step.outputs) {
      producedBy.set(artifact, [...(producedBy.get(artifact) ?? []), step.id]);
    }
  }

  const nodes: GraphNode[] = [
    {
      id: ORCHESTRATOR_ID,
      kind: "orchestrator",
      label: text(workflow?.name),
      sub: "",
      effect: "",
      approval: false,
      manual: false,
      color: "",
    },
  ];
  const edges: GraphEdge[] = [];

  for (const step of wfSteps) {
    nodes.push({
      id: `step:${step.id}`,
      kind: "step",
      label: step.skill || step.id,
      sub: step.name || step.id,
      effect: step.effect,
      approval: step.approval,
      manual: step.manual,
      color: skillColor(step.skill, skills),
    });
  }

  const isEntry = (step: WorkflowStep): boolean =>
    step.inputs.every(
      (artifact) =>
        !(producedBy.get(artifact) ?? []).some((producer) => producer !== step.id),
    );
  for (const step of wfSteps) {
    if (isEntry(step)) {
      edges.push({ from: ORCHESTRATOR_ID, to: `step:${step.id}`, label: "__start" });
    }
  }

  if (showArtifacts) {
    const artifacts = new Set<string>();
    for (const name of strings(workflow?.inputs)) {
      artifacts.add(name);
    }
    for (const name of strings(workflow?.outputs)) {
      artifacts.add(name);
    }
    for (const step of wfSteps) {
      step.inputs.forEach((name) => artifacts.add(name));
      step.outputs.forEach((name) => artifacts.add(name));
    }
    for (const name of artifacts) {
      nodes.push({
        id: `art:${name}`,
        kind: "artifact",
        label: name,
        sub: "",
        effect: "",
        approval: false,
        manual: false,
        color: "",
      });
    }
    for (const step of wfSteps) {
      for (const name of step.inputs) {
        edges.push({ from: `art:${name}`, to: `step:${step.id}`, label: "" });
      }
      for (const name of step.outputs) {
        edges.push({ from: `step:${step.id}`, to: `art:${name}`, label: "" });
      }
    }
  } else {
    for (const step of wfSteps) {
      for (const name of step.inputs) {
        for (const producer of producedBy.get(name) ?? []) {
          if (producer !== step.id) {
            edges.push({ from: `step:${producer}`, to: `step:${step.id}`, label: name });
          }
        }
      }
    }
  }

  return { nodes, edges };
}

function readScenarios(scenarios: JsonDocument | null): FlowScenario[] {
  if (!scenarios) {
    return [];
  }
  return objectRows(scenarios.scenarios).map(({ value }, index) => ({
    id: text(value.id) || `scenario-${index + 1}`,
    given: text(value.given),
    expect: text(value.expect) || "blocked",
    forbidden: strings(value.forbidden),
  }));
}

function isViolation(step: FlowStep, forbidden: Set<string>): boolean {
  if (forbidden.has(step.effect)) {
    return true;
  }
  return step.tools.some((tool) => forbidden.has(tool));
}

function stopMatches(expect: string, step: FlowStep, violation: boolean): boolean {
  switch (expect) {
    case "awaiting-approval":
      return step.approval;
    case "awaiting-manual":
      return step.manual || step.effect === "manual";
    case "awaiting-answer":
      return true;
    case "blocked":
    case "failed":
    case "cancelled":
      return violation || step.effect === "external-write";
    case "uncertain":
      return violation;
    default:
      return false;
  }
}

function traceScenario(steps: FlowStep[], scenario: FlowScenario): TraceEntry[] {
  const forbidden = new Set(scenario.forbidden);
  const completed = scenario.expect === "completed";
  let stopIndex = completed ? steps.length : -1;

  if (!completed) {
    for (let i = 0; i < steps.length; i += 1) {
      const violation = isViolation(steps[i], forbidden);
      if (stopMatches(scenario.expect, steps[i], violation)) {
        stopIndex = i;
        break;
      }
    }
    if (stopIndex === -1) {
      stopIndex = steps.length > 0 ? 0 : -1;
    }
  }

  return steps.map((step, i) => {
    const violation = isViolation(step, forbidden);
    let state: TraceState;
    if (i < stopIndex) {
      state = "run";
    } else if (i === stopIndex) {
      state = "stop";
    } else {
      state = "pending";
    }
    return { step, state, violation };
  });
}

export function AgentFlowPanel({
  workflow,
  scenarios,
}: {
  workflow: JsonDocument | null;
  scenarios: JsonDocument | null;
}) {
  const t = useTranslations();
  const locale = useLocale();
  const steps = useMemo(() => readSteps(workflow), [workflow]);
  const scenarioList = useMemo(() => readScenarios(scenarios), [scenarios]);
  const analysis = useMemo(
    () => (workflow ? analyzeDependencies(workflow) : { edges: [], missing: [], cycles: [] }),
    [workflow],
  );

  const [showArtifacts, setShowArtifacts] = useState(false);
  const graph = useMemo(() => {
    const { nodes: gnodes, edges: gedges } = buildFlow(workflow, showArtifacts);
    const ids = new Set(gnodes.map((node) => node.id));
    const preds = new Map<string, string[]>();
    for (const node of gnodes) {
      preds.set(node.id, []);
    }
    for (const edge of gedges) {
      if (ids.has(edge.from) && preds.has(edge.to)) {
        preds.get(edge.to)!.push(edge.from);
      }
    }
    const rank = new Map<string, number>();
    const compute = (id: string, stack: Set<string>): number => {
      const cached = rank.get(id);
      if (cached !== undefined) {
        return cached;
      }
      if (stack.has(id)) {
        return 0;
      }
      stack.add(id);
      const parents = preds.get(id) ?? [];
      const value =
        parents.length === 0
          ? 0
          : Math.max(...parents.map((parent) => compute(parent, stack) + 1));
      stack.delete(id);
      rank.set(id, value);
      return value;
    };
    for (const node of gnodes) {
      compute(node.id, new Set<string>());
    }

    const kindOrder = (kind: GraphNode["kind"]): number =>
      kind === "orchestrator" ? 0 : kind === "artifact" ? 1 : 2;
    const groups = new Map<number, GraphNode[]>();
    for (const node of gnodes) {
      const r = rank.get(node.id) ?? 0;
      const bucket = groups.get(r) ?? [];
      bucket.push(node);
      groups.set(r, bucket);
    }
    let maxRank = 0;
    let maxCols = 0;
    for (const [r, group] of groups) {
      maxRank = Math.max(maxRank, r);
      maxCols = Math.max(maxCols, group.length);
    }
    const totalWidth =
      maxCols > 0 ? maxCols * (NODE_W + COL_GAP) - COL_GAP : NODE_W;
    const positions = new Map<string, { x: number; y: number }>();
    for (const [r, group] of groups) {
      group.sort(
        (a, b) => kindOrder(a.kind) - kindOrder(b.kind) || a.label.localeCompare(b.label),
      );
      const rowWidth = group.length * (NODE_W + COL_GAP) - COL_GAP;
      const offset = (totalWidth - rowWidth) / 2;
      group.forEach((node, i) => {
        positions.set(node.id, {
          x: CANVAS_PAD + offset + i * (NODE_W + COL_GAP),
          y: CANVAS_PAD + r * (NODE_H + ROW_GAP_V),
        });
      });
    }
    const nodes = gnodes.flatMap((node) => {
      const pos = positions.get(node.id);
      return pos ? [{ node, x: pos.x, y: pos.y }] : [];
    });
    const edges = gedges.flatMap((edge) => {
      const a = positions.get(edge.from);
      const b = positions.get(edge.to);
      if (!a || !b) {
        return [];
      }
      const x1 = a.x + NODE_W / 2;
      const y1 = a.y + NODE_H;
      const x2 = b.x + NODE_W / 2;
      const y2 = b.y;
      const cy = (y1 + y2) / 2;
      return [
        {
          key: `${edge.from}->${edge.to}`,
          from: edge.from,
          label: edge.label,
          path: `M${x1},${y1} C${x1},${cy} ${x2},${cy} ${x2},${y2}`,
          lx: (x1 + x2) / 2,
          ly: cy,
        },
      ];
    });
    const width = CANVAS_PAD * 2 + totalWidth;
    const height = CANVAS_PAD * 2 + maxRank * (NODE_H + ROW_GAP_V) + NODE_H;
    return { nodes, edges, width, height };
  }, [workflow, showArtifacts]);

  const [expandedScenario, setExpandedScenario] = useState<string | null>(null);
  const coverageGroups = useMemo(() => {
    const map = new Map<string, FlowScenario[]>();
    for (const scenario of scenarioList) {
      map.set(scenario.expect, [...(map.get(scenario.expect) ?? []), scenario]);
    }
    const order = (state: string): number => {
      const index = SCENARIO_STATE_ORDER.indexOf(state);
      return index < 0 ? SCENARIO_STATE_ORDER.length : index;
    };
    return [...map.entries()].sort(
      (a, b) => order(a[0]) - order(b[0]) || a[0].localeCompare(b[0]),
    );
  }, [scenarioList]);

  return (
    <div className="page-stack">
      <section className="workspace-panel">
        <p className="eyebrow">{t("agentFlow.flowEyebrow")}</p>
        <h2>{t("agentFlow.flowHeading")}</h2>
        <p className="muted">{t("agentFlow.flowHint")}</p>
        {steps.length === 0 ? (
          <p className="muted">{t("agentFlow.noSteps")}</p>
        ) : (
          <>
            <div className="agent-flow-toolbar">
              <button
                type="button"
                className="button-secondary button-compact"
                onClick={() => setShowArtifacts((value) => !value)}
              >
                {showArtifacts
                  ? t("agentFlow.hideArtifacts")
                  : t("agentFlow.showArtifacts")}
              </button>
            </div>
            <div className="agent-flow-canvas">
              <svg
                className="agent-flow-svg"
                width={graph.width}
                height={graph.height}
                viewBox={`0 0 ${graph.width} ${graph.height}`}
                role="img"
                aria-label={t("agentFlow.flowAria")}
              >
                <defs>
                  <marker
                    id="agent-flow-arrow"
                    markerWidth="9"
                    markerHeight="9"
                    refX="7"
                    refY="3"
                    orient="auto"
                    markerUnits="strokeWidth"
                  >
                    <path d="M0,0 L7,3 L0,6 Z" className="agent-flow-arrowhead" />
                  </marker>
                </defs>
                {graph.edges.map((edge) => (
                  <g key={edge.key}>
                    <path
                      d={edge.path}
                      className="agent-flow-edge"
                      markerEnd="url(#agent-flow-arrow)"
                    />
                    {edge.from === ORCHESTRATOR_ID || edge.label ? (
                      <text
                        x={edge.lx}
                        y={edge.ly}
                        className="agent-flow-elabel"
                        textAnchor="middle"
                      >
                        {edge.from === ORCHESTRATOR_ID
                          ? t("agentFlow.start")
                          : short(edge.label, 14)}
                      </text>
                    ) : null}
                  </g>
                ))}
                {graph.nodes.map(({ node, x, y }) => {
                  if (node.kind === "orchestrator") {
                    return (
                      <g key={node.id} className="agent-flow-orch">
                        <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={9} />
                        <text
                          x={x + NODE_W / 2}
                          y={y + NODE_H / 2 + 5}
                          className="agent-flow-orch-label"
                          textAnchor="middle"
                        >
                          {short(node.label || t("agentFlow.orchestrator"), 20)}
                        </text>
                      </g>
                    );
                  }
                  if (node.kind === "artifact") {
                    return (
                      <g key={node.id} className="agent-flow-anode">
                        <rect
                          x={x}
                          y={y}
                          width={NODE_W}
                          height={NODE_H}
                          rx={NODE_H / 2}
                        />
                        <text
                          x={x + NODE_W / 2}
                          y={y + NODE_H / 2 + 4}
                          className="agent-flow-alabel"
                          textAnchor="middle"
                        >
                          {short(node.label, 20)}
                        </text>
                      </g>
                    );
                  }
                  return (
                    <g
                      key={node.id}
                      className={`agent-flow-gnode agent-flow-effect-${node.effect}`}
                    >
                      <rect x={x} y={y} width={NODE_W} height={NODE_H} rx={9} />
                      <circle
                        cx={x + 16}
                        cy={y + NODE_H / 2}
                        r={6}
                        fill={node.color}
                      />
                      <text
                        x={x + 30}
                        y={y + 26}
                        className="agent-flow-gid"
                        textAnchor="start"
                      >
                        {short(node.label, 15)}
                      </text>
                      <text
                        x={x + 30}
                        y={y + 44}
                        className="agent-flow-gmeta"
                        textAnchor="start"
                      >
                        {short(node.sub, 17)}
                      </text>
                      {node.approval || node.manual ? (
                        <>
                          <circle
                            cx={x + NODE_W - 13}
                            cy={y + 13}
                            r={5}
                            className={
                              node.approval
                                ? "agent-flow-mark-approval"
                                : "agent-flow-mark-manual"
                            }
                          />
                          <title>
                            {node.approval
                              ? t("agentFlow.badgeApproval")
                              : t("agentFlow.badgeManual")}
                          </title>
                        </>
                      ) : null}
                    </g>
                  );
                })}
              </svg>
            </div>
            <div className="agent-flow-legend">
              <span className="agent-flow-legend-item agent-flow-legend-step">
                {t("agentFlow.legendStep")}
              </span>
              <span className="agent-flow-legend-item agent-flow-legend-artifact">
                {t("agentFlow.legendArtifact")}
              </span>
              <span className="agent-flow-legend-item agent-flow-effect-read">
                {t("agentFlow.effectRead")}
              </span>
              <span className="agent-flow-legend-item agent-flow-effect-local">
                {t("agentFlow.effectLocal")}
              </span>
              <span className="agent-flow-legend-item agent-flow-effect-external-write">
                {t("agentFlow.effectExternalWrite")}
              </span>
              <span className="agent-flow-legend-item agent-flow-effect-manual">
                {t("agentFlow.effectManual")}
              </span>
            </div>
            <p className="muted agent-flow-note">{t("agentFlow.singleAgentNote")}</p>
            {analysis.missing.map((item) => (
              <p className="error-text" key={`${item.stepId}-${item.dependencyId}`}>
                {t("agentFlow.missingNode", {
                  stepId: item.stepId,
                  dependencyId: item.dependencyId,
                })}
              </p>
            ))}
            {analysis.cycles.map((cycle) => (
              <p className="error-text" key={cycle.join("-")}>
                {t("agentFlow.cycle", { cycle: cycle.join(" → ") })}
              </p>
            ))}
          </>
        )}
      </section>

      <section className="workspace-panel">
        <p className="eyebrow">{t("agentFlow.simEyebrow")}</p>
        <h2>{t("agentFlow.simHeading")}</h2>
        <p className="muted">{t("agentFlow.simHint")}</p>
        {scenarioList.length === 0 || steps.length === 0 ? (
          <p className="muted">{t("agentFlow.noScenarios")}</p>
        ) : (
          <div className="scenario-coverage">
            {coverageGroups.map(([state, list]) => {
              const openScenario = list.find(
                (scenario) => scenario.id === expandedScenario,
              );
              return (
                <div className="scenario-group" key={state}>
                  <div className="scenario-group-head">
                    <span className={`scenario-state scenario-state-${state}`}>
                      {state}
                    </span>
                    <span className="muted">{list.length}</span>
                  </div>
                  <div className="scenario-chips">
                    {list.map((scenario) => {
                      const chipLabel = scenarioLabel(scenario.id, locale);
                      const isOpen = expandedScenario === scenario.id;
                      return (
                        <button
                          type="button"
                          key={scenario.id}
                          className={`scenario-chip scenario-state-${state}${isOpen ? " is-open" : ""}`}
                          aria-expanded={isOpen}
                          onClick={() =>
                            setExpandedScenario(isOpen ? null : scenario.id)
                          }
                        >
                          <code>{scenario.id}</code>
                          {chipLabel ? (
                            <span className="scenario-chip-label">{chipLabel}</span>
                          ) : null}
                        </button>
                      );
                    })}
                  </div>
                  {openScenario ? (
                    <div className="scenario-detail">
                      {openScenario.given ? (
                        <p className="agent-sim-given">{openScenario.given}</p>
                      ) : null}
                      {openScenario.forbidden.length > 0 ? (
                        <p className="agent-flow-needs">
                          {t("agentFlow.forbiddenLabel", {
                            forbidden: openScenario.forbidden.join(", "),
                          })}
                        </p>
                      ) : null}
                      <ol className="agent-sim-trace">
                        {traceScenario(steps, openScenario).map(
                          ({ step, state: stepState, violation }) => (
                            <li
                              className={`agent-sim-step agent-sim-${stepState}`}
                              key={step.id}
                            >
                              <span className="agent-sim-state">
                                {t(`agentFlow.state.${stepState}`)}
                              </span>
                              <code>{step.id}</code>
                              {violation ? (
                                <span className="agent-sim-violation">
                                  {t("agentFlow.violation")}
                                </span>
                              ) : null}
                            </li>
                          ),
                        )}
                      </ol>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
