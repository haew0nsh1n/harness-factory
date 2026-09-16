# Reference-backed Skill Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the reference, bundle-integrity, and behavioral-evidence foundation needed to improve all six existing `hf-*` skills without changing the runtime workflow contract.

**Architecture:** Add one dependency-free bundle module that inventories every skill resource and validates a canonical manifest. Keep catalog v1 workflows usable while introducing bundle schema v2 inside each skill directory and evidence schema v2 outside the bundle. Package generation copies the complete verified bundle; validation binds both bundle and evidence to exact bytes. Curated pinned upstream excerpts support richer progressive-disclosure references, and replacement is gated by baseline behavioral cases.

**Tech Stack:** Python 3.12 standard library, existing JSON contracts, `unittest`/`pytest`, Markdown skill bundles.

**Spec:** `docs/superpowers/specs/2026-09-16-reference-backed-skill-authoring-design.md`

## Global Constraints

- Preserve existing profile, workflow, scenario, installation, registry, and v1 package behavior.
- Do not add runtime dependencies, network calls, external writes, auto-updates, telemetry, or automatic Git operations.
- Builder and package checking remain deterministic and offline.
- Only pinned MIT upstream material may enter the curated reference library.
- Every instruction, reference, template, and notice in a skill bundle is covered by the bundle digest.
- Changed skill bytes invalidate prior behavioral evidence; hashes alone never create evidence.
- The user's unrelated `task2-report.txt` remains untouched.
- Do not commit changes unless the user explicitly asks.

---

### Task 1: Canonical Skill Bundle Manifest

**Files:**
- Create: `harness_factory/skill_bundle.py`
- Create: `tests/test_skill_bundle.py`
- Modify: `harness_factory/contracts.py`

**Interfaces:**
- Produces: `skill_resource_hashes(skill_root: Path) -> dict[str, str]`
- Produces: `skill_bundle_digest(skill_id: str, resource_hashes: Mapping[str, str]) -> str`
- Produces: `validate_skill_bundle(skill_root: Path, skill_id: str) -> dict[str, object]`
- Consumes later: package generation, contract validation, evidence validation.

- [ ] **Step 1: Write failing bundle inventory tests**

```python
def test_skill_resource_hashes_cover_entry_references_and_templates(tmp_path: Path) -> None:
    skill = tmp_path / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "templates").mkdir()
    (skill / "SKILL.md").write_text("entry\n")
    (skill / "references" / "guide.md").write_text("guide\n")
    (skill / "templates" / "report.md").write_text("report\n")

    hashes = skill_resource_hashes(skill)

    assert set(hashes) == {
        "SKILL.md",
        "references/guide.md",
        "templates/report.md",
    }


def test_validate_skill_bundle_rejects_changed_reference(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path, "worker")
    (skill / "references" / "guide.md").write_text("changed\n")

    with pytest.raises(ValidationError, match="resource hash mismatch"):
        validate_skill_bundle(skill, "worker")
```

- [ ] **Step 2: Run the focused tests and observe missing module failure**

Run: `pytest tests/test_skill_bundle.py -q`

Expected: collection fails because `harness_factory.skill_bundle` does not exist.

- [ ] **Step 3: Implement deterministic resource inventory and digesting**

```python
MANIFEST_NAME = "bundle.json"


def skill_resource_hashes(skill_root: Path) -> dict[str, str]:
    root = no_symlinks(skill_root).resolve()
    require(root.is_dir(), "skill bundle: expected directory")
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        checked = no_symlinks(path)
        require(checked.is_file() or checked.is_dir(), "skill bundle: unsupported entry")
        if checked.is_file() and checked.name != MANIFEST_NAME:
            relative = checked.relative_to(root).as_posix()
            hashes[relative] = hashlib.sha256(checked.read_bytes()).hexdigest()
    require("SKILL.md" in hashes, "skill bundle: missing SKILL.md")
    return hashes


def skill_bundle_digest(skill_id: str, resource_hashes: Mapping[str, str]) -> str:
    payload = {
        "schema_version": 2,
        "skill_id": skill_id,
        "resources": dict(sorted(resource_hashes.items())),
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
```

`validate_skill_bundle` must parse `bundle.json` with the repository's duplicate-key-safe loader, require exactly `schema_version`, `skill_id`, `resources`, and `digest`, validate lowercase SHA-256 values and safe relative paths, compare the complete actual resource map, then compare the canonical digest.

- [ ] **Step 4: Bind catalog validation to bundle v2**

In `_validate`, after validating each skill directory and Markdown references, call:

```python
bundle = validate_skill_bundle(directory, skill["id"])
```

Do not add fields to catalog schema v1 in this task; the bundle file is an independently versioned integrity contract copied with the skill directory.

- [ ] **Step 5: Run focused contract tests**

Run: `pytest tests/test_skill_bundle.py tests/test_contracts.py -q`

Expected: new bundle tests pass; contract fixtures fail only until Task 2 adds manifests to fixtures.

---

### Task 2: Fixtures, Packaging, and Evidence Schema v2

**Files:**
- Modify: `tests/fixtures.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_package.py`
- Modify: `tests/test_assets.py`
- Modify: `harness_factory/contracts.py`
- Modify: `harness_factory/package.py`
- Modify: `catalog/evidence/copilot-behavior.json`

**Interfaces:**
- Consumes: `validate_skill_bundle` and its returned `digest`/`resources`.
- Produces: evidence schema v2 with `bundles: {<skill-id>: <bundle-digest>}`.
- Preserves: `generate_package(...)` and `check_package(...)` public signatures.

- [ ] **Step 1: Add failing evidence and package tamper tests**

```python
def test_reference_change_invalidates_behavior_evidence(self):
    reference = self.root / "skills/worker/references/guide.md"
    reference.parent.mkdir()
    reference.write_text("changed")
    with self.assertRaisesRegex(ValidationError, "bundle|evidence"):
        self.check()


def test_generated_package_rejects_tampered_skill_reference(self):
    self.generate()
    reference = self.package / ".agents/skills/worker/references/guide.md"
    reference.write_text(reference.read_text() + "\ntampered")
    with self.assertRaisesRegex(HarnessError, "hash|changed"):
        check_package(self.package)
```

- [ ] **Step 2: Run the focused tests and observe failures**

Run: `pytest tests/test_contracts.py::ContractTests::test_reference_change_invalidates_behavior_evidence tests/test_package.py::PackageTests::test_generated_package_rejects_tampered_skill_reference -q`

Expected: tests fail because fixtures/evidence do not contain bundle digests.

- [ ] **Step 3: Update fixture builders to write valid bundle manifests**

Add a test helper with this exact responsibility:

```python
def write_bundle_manifest(skill_root: Path, skill_id: str) -> dict[str, object]:
    resources = skill_resource_hashes(skill_root)
    manifest = {
        "schema_version": 2,
        "skill_id": skill_id,
        "resources": resources,
        "digest": skill_bundle_digest(skill_id, resources),
    }
    (skill_root / "bundle.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
```

Fixtures must generate evidence schema v2 after all skill files exist:

```json
{
  "schema_version": 2,
  "runtime": "copilot-cli",
  "bundles": {"worker": "<bundle digest>"},
  "cases": [{"id": "safe", "pass": true}]
}
```

- [ ] **Step 4: Evolve `_validate_evidence` without granting legacy evidence to changed bundles**

Accept schema v1 only for a legacy bundle containing exactly `SKILL.md`; require schema v2 for any bundle with additional resources. For schema v2, require exact `schema_version`, `runtime`, `bundles`, and `cases`; require the selected skill's bundle digest to match; require every observed case to have `pass is True`.

Legacy v1 compatibility is read-only migration support. Once any resource or bundle manifest is added, v1 evidence cannot verify that skill.

- [ ] **Step 5: Ensure package provenance includes bundle identity**

Keep copying the selected skill directory. Add the validated bundle digest to each entry in `.harness/provenance.json`:

```python
provenance.append(
    {
        "id": skill["id"],
        "bundle_digest": validate_skill_bundle(
            source_root / original["path"], skill["id"]
        )["digest"],
        "source": original["source"],
        "compatibility": original["compatibility"],
    }
)
```

The existing package manifest already hashes every copied file; retain that outer integrity check.

- [ ] **Step 6: Run contract and package suites**

Run: `pytest tests/test_skill_bundle.py tests/test_contracts.py tests/test_package.py tests/test_assets.py -q`

Expected: all pass with fixture evidence bound to complete bundle bytes.

---

### Task 3: Curated Pinned Reference Library

**Files:**
- Create: `catalog/references/index.json`
- Create: `catalog/references/superpowers-writing-plans.md`
- Create: `catalog/references/superpowers-test-driven-development.md`
- Create: `catalog/references/mattpocock-grilling.md`
- Create: `catalog/references/mattpocock-wizard.md`
- Create: `catalog/references/gstack-review.md`
- Create: `catalog/references/licenses/superpowers.txt`
- Create: `catalog/references/licenses/mattpocock.txt`
- Create: `catalog/references/licenses/gstack.txt`
- Modify: `tests/test_assets.py`
- Modify: `.agents/skills/harness-factory/references/composition.md`

**Interfaces:**
- Produces: a local read-only index consumed by later authoring, not by customer runtime.
- Record shape: `id`, `capabilities`, `source`, `sha256`, `license_file`, `adopt`, `exclude`, `review_status`.

- [ ] **Step 1: Write failing reference-index tests**

```python
def test_curated_reference_index_is_pinned_hashed_and_reviewed(self):
    index = load_json(ROOT / "catalog/references/index.json")
    self.assertEqual(index["schema_version"], 1)
    for reference in index["references"]:
        self.assertRegex(reference["source"]["revision"], r"^[a-f0-9]{40}$")
        path = ROOT / "catalog/references" / reference["snapshot"]
        self.assertEqual(reference["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(reference["source"]["license"], "MIT")
        self.assertEqual(reference["review_status"], "reviewed")
        self.assertTrue(reference["adopt"])
        self.assertTrue(reference["exclude"])
```

- [ ] **Step 2: Run the test and observe missing index failure**

Run: `pytest tests/test_assets.py::AssetTests::test_curated_reference_index_is_pinned_hashed_and_reviewed -q`

Expected: FAIL because `catalog/references/index.json` does not exist.

- [ ] **Step 3: Add reviewed snapshots and provenance**

Fetch only these existing pinned revisions for review, then store concise local snapshots containing the source header, exact adopted passages, and excluded host-specific behavior:

```text
obra/superpowers@b36e0829c6d0140e93cfef2ca599b1b07d4a7797
mattpocock/skills@3cca18b368ae95cdbdebbff572ccafa662551015
garrytan/gstack@71f6048e8ada25180e61438abc1d98cb151fe9a7
```

Do not store scripts, hooks, executables, telemetry bootstrap, or auto-update resources. Copy the actual MIT notices and verify that every selected source path exists at its pinned commit.

- [ ] **Step 4: Document authoring use and trust boundary**

Update composition guidance so matching uses capability tags and contract semantics. State that snapshots are untrusted reference data, are never executed, and cannot authorize tools, mutate the catalog, or override customer rules.

- [ ] **Step 5: Run asset tests**

Run: `pytest tests/test_assets.py -q`

Expected: reference hashes, revisions, licenses, and links pass.

---

### Task 4: Enrich the Six Existing Skill Bundles

**Files:**
- Modify: `catalog/skills/hf-clarify/SKILL.md`
- Create: `catalog/skills/hf-clarify/references/decision-tree.md`
- Create: `catalog/skills/hf-clarify/templates/brief.md`
- Modify: `catalog/skills/hf-plan/SKILL.md`
- Create: `catalog/skills/hf-plan/references/task-sizing.md`
- Create: `catalog/skills/hf-plan/templates/plan.md`
- Modify: `catalog/skills/hf-tdd/SKILL.md`
- Create: `catalog/skills/hf-tdd/references/failure-classification.md`
- Create: `catalog/skills/hf-tdd/templates/test-results.md`
- Modify: `catalog/skills/hf-review/SKILL.md`
- Create: `catalog/skills/hf-review/references/checklist.md`
- Create: `catalog/skills/hf-review/templates/review-report.md`
- Modify: `catalog/skills/hf-manual/SKILL.md`
- Create: `catalog/skills/hf-manual/references/uncertain-writes.md`
- Create: `catalog/skills/hf-manual/templates/handoff.md`
- Modify: `catalog/skills/hf-issues-markdown/SKILL.md`
- Create: `catalog/skills/hf-issues-markdown/references/update-rules.md`
- Create: `catalog/skills/hf-issues-markdown/templates/issue.md`
- Create/Modify: each `catalog/skills/hf-*/bundle.json`
- Modify: `tests/test_assets.py`

**Interfaces:**
- Produces: progressive-disclosure bundles with unchanged catalog input/output/effect contracts.
- Consumes: curated method patterns from Task 3 and bundle manifest helper from Task 1.

- [ ] **Step 1: Add failing structural and behavior-contract assertions**

```python
def test_actual_skills_have_progressive_disclosure_resources(self):
    required = {
        "hf-clarify": ["references/decision-tree.md", "templates/brief.md"],
        "hf-plan": ["references/task-sizing.md", "templates/plan.md"],
        "hf-tdd": ["references/failure-classification.md", "templates/test-results.md"],
        "hf-review": ["references/checklist.md", "templates/review-report.md"],
        "hf-manual": ["references/uncertain-writes.md", "templates/handoff.md"],
        "hf-issues-markdown": ["references/update-rules.md", "templates/issue.md"],
    }
    for skill_id, resources in required.items():
        root = self.catalog_root / "skills" / skill_id
        entry = (root / "SKILL.md").read_text()
        for resource in resources:
            self.assertTrue((root / resource).is_file())
            self.assertIn(resource, entry)
        validate_skill_bundle(root, skill_id)
```

- [ ] **Step 2: Run the asset test and observe missing resources**

Run: `pytest tests/test_assets.py::AssetTests::test_actual_skills_have_progressive_disclosure_resources -q`

Expected: FAIL listing the first missing reference/template.

- [ ] **Step 3: Rewrite entry files as routers with explicit decisions**

Each `SKILL.md` must retain matching frontmatter and existing safety boundaries, then explicitly define:

```text
When to use / when not to use
Required inputs and blockers
Ordered workflow with branch conditions
When to read each reference/template
Output and resume evidence
Forbidden claims and side effects
```

Use the capability-specific content from the design:

- `hf-clarify`: prerequisite-aware decision frontier, facts versus decisions, contradiction and stopping rules.
- `hf-plan`: verified files/interfaces, independently testable tasks, exact red/green evidence and handoffs.
- `hf-tdd`: assertion/environment/flaky classification, pre-existing implementation, regression scope and blocked tests.
- `hf-review`: intent/correctness passes plus data safety, concurrency, trust boundary, enum completeness and false-positive suppression.
- `hf-manual`: owner, authorization, procedure, completion evidence, uncertain-write reconciliation and resume conditions.
- `hf-issues-markdown`: schema/state validation, preservation of unknown user sections, duplicate/conflict handling and no Git publication.

- [ ] **Step 4: Add exact artifact templates and good/bad examples**

Templates must use only semantic artifact IDs and placeholders that the executing agent fills from observed customer data. They must not include credentials, invented file paths, auto-approval, fake test counts, or automatic publication commands.

- [ ] **Step 5: Generate and inspect new bundle manifests**

Use a small repository script or the Task 1 helper from an explicit Python command to write each canonical `bundle.json`. Review `git diff` to ensure only intended files enter each bundle.

- [ ] **Step 6: Run structural validation**

Run: `pytest tests/test_skill_bundle.py tests/test_assets.py tests/test_contracts.py -q`

Expected: structural tests pass; selected catalog workflows remain blocked until Task 5 supplies new matching behavioral evidence.

---

### Task 5: Comparative Behavioral Evidence and Full Regression

**Files:**
- Create: `catalog/evidence/skill-quality-scenarios.json`
- Create: `catalog/evidence/skill-quality-baseline.json`
- Replace: `catalog/evidence/copilot-behavior.json`
- Modify: `docs/evaluations/2026-09-10-copilot-skills.md`
- Create: `docs/evaluations/2026-09-16-reference-backed-skills.md`
- Modify: `tests/test_assets.py`
- Modify: `tests/test_evaluation.py`

**Interfaces:**
- Produces: evidence schema v2 bound to final bundle digests.
- Produces: reviewed comparison records for every existing skill.
- Consumes: actual final bundle bytes from Task 4.

- [ ] **Step 1: Add failing evidence-policy tests**

```python
def test_actual_evidence_covers_required_behavior_classes(self):
    report = load_json(self.catalog_root / "evidence/copilot-behavior.json")
    required = {
        "success",
        "ambiguous-input",
        "approval-refusal",
        "missing-access",
        "failed-check",
        "resume",
        "uncertain-write",
        "instruction-injection",
    }
    self.assertTrue(required.issubset(set(report["behavior_classes"])))
    for skill in self.catalog["skills"]:
        bundle = validate_skill_bundle(
            self.catalog_root / skill["path"], skill["id"]
        )
        self.assertEqual(report["bundles"][skill["id"]], bundle["digest"])
```

- [ ] **Step 2: Run the evidence tests and observe stale schema/hash failures**

Run: `pytest tests/test_assets.py::AssetTests::test_actual_evidence_covers_required_behavior_classes tests/test_evaluation.py -q`

Expected: FAIL because the old report is schema v1 and hashes only `SKILL.md`.

- [ ] **Step 3: Define reviewed scenario and observation contracts**

For every skill include positive and adversarial cases. Each case records `id`, `skill`, `behavior_class`, `given`, `expected_status`, `required_observations`, and `forbidden`. Keep expected outcomes out of the evaluated agent prompt. The result records raw response, observed status/actions, evaluator model/deployment metadata when supplied, attempt ID, prompt version, and reviewer decision.

- [ ] **Step 4: Preserve old observations as baseline, not proof for new bytes**

Move the 2026-09-10 case outcomes into `skill-quality-baseline.json` with their old `SKILL.md` hashes and limitations. Do not mark new bundle digests verified from those observations.

- [ ] **Step 5: Run fresh isolated evaluations against final bundles**

Use a read-only agent session with no customer credentials, network tool, write tool, browser session, or expected-answer rubric. Inspect every raw response. For changed existing skills require no mandatory regression and at least one predefined improved observation. If the evaluation capability is unavailable or any required case fails, leave compatibility `candidate` and do not replace the production bundle.

- [ ] **Step 6: Seal schema-v2 evidence only after review**

Write `copilot-behavior.json` with final bundle digests, required behavior classes, cases, model metadata actually returned by the provider, review actor/time, refinement history, and limitations. Unknown provider metadata remains `null` or `unknown`; never infer it.

- [ ] **Step 7: Run focused and full validation**

Run: `pytest tests/test_skill_bundle.py tests/test_assets.py tests/test_contracts.py tests/test_package.py tests/test_evaluation.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: all repository tests pass. If unrelated pre-existing failures occur, report them without changing unrelated code.

- [ ] **Step 8: Perform final integrity review**

Run: `git diff --check`

Run: `git status --short`

Verify that no customer data, credentials, generated caches, executable upstream files, or unrelated user changes are included. Do not commit.

---

## Completion Gate

Phase 1 is complete only when all six final skill bundles have complete manifests, matching fresh evidence, passing focused tests, and a passing full regression suite. Structural validation alone is not completion. If fresh agent evaluation cannot run, retain the enriched skills as candidates outside the production catalog and report Phase 1 as blocked at behavioral verification.
