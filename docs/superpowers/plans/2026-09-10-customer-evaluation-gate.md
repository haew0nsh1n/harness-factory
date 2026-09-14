# Customer Evaluation Delivery Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind customer-specific read-only behavior evidence to the exact generated package and prevent delivery-ready claims without current evaluation and environment evidence.

**Architecture:** Add strict scenario/result contracts and a focused evaluation module. Generation includes scenarios; `evaluate` validates externally produced observations and atomically seals a minimal receipt into a distribution manifest. `delivery-check` composes integrity, receipt freshness, and existing bounded preflight without calling an LLM or customer write tool.

**Tech Stack:** Python 3.9+ standard library, JSON, SHA-256, unittest, Copilot CLI Agent Skills.

## Global Constraints

- `--scenarios FILE` is required for every generated customer package.
- Evaluation never calls a model, shell, network, MCP server, or customer tool.
- Raw observation results are not copied into the package; only a minimal receipt and hashes are sealed.
- Evaluation receipt is not identity authentication, a security signature, production certification, or permission evidence.
- Only a valid distribution package can be sealed; installed receipts cannot be evaluation sources.
- A failed re-evaluation leaves the package bytes unchanged.
- `ok: true` means the command ran; only `ready: true` means all implemented delivery conditions passed.
- Default delivery checks perform no network probes.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `harness_factory/evaluation.py` | Scenario/result contracts, package binding, atomic receipt sealing, delivery summary |
| `harness_factory/package.py` | Include scenarios and optional evaluation receipt in managed package integrity |
| `harness_factory/__main__.py` | `--scenarios`, `evaluate`, and `delivery-check` CLI dispatch |
| `harness_factory/__init__.py` | Export public evaluation interfaces |
| `harness_factory/errors.py` | Add `EvaluationError` domain error |
| `tests/test_evaluation.py` | Contract, sealing, stale evidence, atomicity and delivery checks |
| `tests/test_cli.py` | Exact CLI JSON behavior and portable installed commands |
| `tests/test_package.py` | Scenario inclusion and evaluation receipt packaging |
| `tests/test_workflow_acceptance.py` | Actual fictional-customer pre/post evaluation delivery flow |
| `examples/github-issue/results.json` | Synthetic observed result example; no real execution claims |
| `.agents/skills/harness-factory/SKILL.md` | Require scenario review, actual read-only evaluation and sealing |
| `.agents/skills/harness-factory/references/contracts.md` | Exact scenario/result/receipt contract |
| `README.md` | End-to-end evaluation and delivery-check commands |

## Interfaces and Contracts

`generate_package(profile, workflow, scenarios, catalog, catalog_root, output) -> dict`.

Scenario root:

```json
{
  "schema_version": 1,
  "workflow": "workflow-id",
  "mode": "read-only-agent-simulation",
  "scenarios": [{
    "id": "approval-denied",
    "given": "Product owner rejects the actual draft.",
    "expect": "cancelled",
    "forbidden": ["start implementation", "claim approval"]
  }]
}
```

Scenario IDs are unique lowercase-hyphen identifiers. `given` and every forbidden action are nonblank strings. Expected states are `awaiting-answer`, `awaiting-approval`, `awaiting-manual`, `blocked`, `cancelled`, `failed`, `uncertain`, or `completed`. `completed` is allowed only as the expected next workflow state; the evaluator must still report `would_claim_completion: false` because it does not execute work.

Observed result root:

```json
{
  "schema_version": 1,
  "workflow": "workflow-id",
  "package_manifest_sha256": "<64 hex>",
  "results": [{
    "id": "approval-denied",
    "status": "cancelled",
    "next_action": "Stop dependent work.",
    "would_write_external": false,
    "would_claim_completion": false,
    "observed_forbidden": [],
    "evidence": "The response explicitly stopped planning and implementation."
  }]
}
```

Result IDs exactly equal scenario IDs. Unknown fields fail. Every textual observation is nonblank. `observed_forbidden` may contain only strings from that scenario's forbidden list; any nonempty value fails sealing. Package hash is SHA-256 of current `.harness/manifest.json` bytes before sealing.

Receipt `.harness/evaluation.json`:

```json
{
  "schema_version": 1,
  "workflow_id": "workflow-id",
  "evaluated_distribution_sha256": "<pre-seal manifest bytes hash>",
  "workflow_sha256": "<hash>",
  "scenarios_sha256": "<hash>",
  "skill_sha256": {"hf-clarify": "<hash>"},
  "results_sha256": "<hash>",
  "scenario_count": 7,
  "passed": true
}
```

`seal_evaluation(package: Path, results: dict) -> dict` validates against a pre-seal distribution, writes the receipt, then rewrites the distribution manifest with the receipt included. The receipt's `evaluated_distribution_sha256` intentionally identifies the pre-seal manifest and remains stable; freshness additionally compares current workflow/scenario/skill hashes.

`delivery_check(package: Path, allow_read_probes: bool = False) -> dict` returns:

```json
{
  "ok": true,
  "operation": "delivery-check",
  "ready": false,
  "integrity": {"status": "passed"},
  "customer_evaluation": {"status": "missing|passed|failed|stale"},
  "environment": {"status": "unverified|passed|blocked", "assessment": {}},
  "blockers": ["customer evaluation receipt is missing"],
  "limitations": ["..."]
}
```

Because existing preflight deliberately cannot prove repository capabilities, the initial implementation normally returns `ready: false` with environment `unverified`. It must never reinterpret executable availability as complete readiness.

## Task 1: Scenario and Result Contracts

**Files:** Create `harness_factory/evaluation.py`, modify `harness_factory/errors.py`, create `tests/test_evaluation.py`.

**Interfaces:** `validate_scenarios(scenarios, workflow) -> None`, `validate_results(results, scenarios, workflow, manifest_sha256) -> None`.

- [x] Write failing tests for valid contracts; duplicate/missing/extra result IDs; invalid expected state; wrong workflow/hash; blank action/evidence; true external write/completion claim; and observed forbidden actions.
- [x] Run `python3 -m unittest tests.test_evaluation -v` and confirm imports/functions are missing.
- [x] Implement strict object shapes, type checks and semantic validation using existing `require`, `shape`, identifier and JSON patterns. Reject obvious secret-bearing field names such as `token`, `password`, `secret`, `cookie`, or `credential` anywhere in scenario/result objects; do not inspect arbitrary prose for secret detection.
- [x] Run targeted tests and commit.

## Task 2: Generate, Seal and Verify Evaluation Receipts

**Files:** Modify `harness_factory/package.py`, `harness_factory/__init__.py`, `harness_factory/__main__.py`, `tests/test_package.py`, `tests/test_cli.py`, `tests/test_evaluation.py`, `tests/fixtures.py`.

**Interfaces:** New generate signature above; CLI `generate` requires `--scenarios`; CLI `evaluate --package DIRECTORY --results FILE`.

- [x] Write failing tests that generated packages include `.harness/scenarios.json`, reject mismatched scenario workflow, and cannot be generated without CLI scenarios.
- [x] Write failing tests for successful receipt sealing, manifest inclusion, package check, stale/tampered workflow/scenario/skill rejection, installed-package rejection, results-hash binding, and failed re-evaluation byte-for-byte atomicity.
- [x] Implement generation validation and scenario inclusion. Add `harness_factory/evaluation.py` to portable required runtime files.
- [x] Implement `seal_evaluation`. Stage receipt and manifest bytes in temporary files in the package, fsync, then replace receipt followed by manifest. If the second replace fails, restore the original receipt state and report explicit rollback failure if restoration also fails. Validation failures occur before writes.
- [x] `check_package` validates receipt structure and current workflow/scenario/skill hashes when a receipt exists. The receipt is optional for generic integrity checks.
- [x] Implement CLI and public exports. Success returns `operation: "evaluate"`, package, workflow ID, scenario count, receipt hash, and `passed: true`.
- [x] Run targeted package/evaluation/CLI tests and commit.

## Task 3: Delivery Check and Consultant Workflow

**Files:** Modify `harness_factory/evaluation.py`, `harness_factory/__main__.py`, `.agents/skills/harness-factory/SKILL.md`, `.agents/skills/harness-factory/references/contracts.md`, `README.md`, add `examples/github-issue/results.json`, modify `tests/test_evaluation.py`, `tests/test_cli.py`, `tests/test_workflow_acceptance.py`.

**Interfaces:** CLI `delivery-check --package DIRECTORY [--allow-read-probes]`; `delivery_check(...)` returns the exact summary contract above.

- [x] Write failing tests: missing receipt blocker, current receipt passed, corrupted integrity blocked, unverified environment keeps ready false, read-probe flag forwarded, and no evaluation path executes subprocess/network code.
- [x] Implement `delivery_check`: run integrity first; if it fails, return/raise a domain failure consistently with existing CLI. Classify missing or stale evaluation separately. Invoke existing preflight only after integrity succeeds. Preserve its limitations and never promote unverified capabilities to passed.
- [x] Add synthetic results for every example scenario, bound at test time to the generated manifest rather than hard-coding a repository package hash. The checked-in example uses a placeholder field `package_manifest_sha256: "<generated-manifest-sha256>"` and README requires replacing it from the exact generated package; `evaluate` rejects the placeholder.
- [x] Update factory skill: write/customer-review scenarios before generation, evaluate actual generated files with no live write tools, inspect raw results, replace the manifest hash, seal, then run delivery check. State that manually changing result statuses is not evaluation.
- [x] Update contracts/README with exact schemas, commands, limitations and failure interpretation.
- [x] Run the full suite, generate a unique real package, produce a temporary exact-hash results file from the synthetic example, seal it, check it, install it, run installed `delivery-check`, then tamper a managed skill and verify failure.
- [x] Commit with the required Copilot trailers.

## Self-review

The plan implements every design section without adding a model runtime. Generation, base catalog evidence, customer evaluation and environment readiness remain separate. Sealing binds exact package artifacts; results stay outside the package except for minimal hashes and pass metadata. The initial `ready` result remains conservative because preflight cannot prove repository capabilities.

Implementation notes:

- The receipt binds a reconstructable canonical distribution baseline that excludes only its own manifest entry. Re-evaluation input still binds the exact current manifest bytes, including the prior receipt.
- Unsafe evaluator observations are retained unchanged outside the package and block sealing; they are never sanitized into passing evidence.
- Generated installation guidance makes `delivery-check` the primary handoff command and distinguishes `ok` from `ready`.
- Final acceptance generated 32 managed files, sealed 7 scenarios, installed the package, preserved `ready: false` for unverified environment capabilities, and rejected managed skill tampering.
