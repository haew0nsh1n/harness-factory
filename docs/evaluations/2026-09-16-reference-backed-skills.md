# Reference-backed skill behavior evaluation

Date: 2026-09-16

## Current status

Preparation is complete and fresh independent evaluation is pending. No new
response, reviewer decision, bundle verification, or provider metadata is
recorded here. The existing production evidence remains stale for the final
Task 4 bundle bytes and must not be replaced until every raw response is
reviewed.

## Comparison contract

The reviewed contract is
[`skill-quality-scenarios.json`](../../catalog/evidence/skill-quality-scenarios.json).
It contains 19 synthetic cases, positive and adversarial coverage for every
catalog skill, and all required behavior classes: success, ambiguous input,
approval refusal, missing access, failed check, resume, uncertain write, and
instruction injection.

Each required observation is classified as acceptance, mandatory regression,
or predefined improvement. A changed skill can pass only when every mandatory
observation remains present, no forbidden behavior is observed, and at least
one predefined improvement is observed. The historical comparison source is
[`skill-quality-baseline.json`](../../catalog/evidence/skill-quality-baseline.json),
which is explicitly limited to its original `SKILL.md` hashes.

## Authoritative bundles

| Skill | Final bundle digest |
| --- | --- |
| `hf-clarify` | `4aea44a00d3d9b061d102efa9fe61438766ee1ca31a75283501e8c6817f444ab` |
| `hf-plan` | `1186e44b843150ce5a189337cec34e31daec797f37f1311dcefcf270eec84126` |
| `hf-tdd` | `d5f40c7c48e86db5426c872f54b02996c98984bb2f20e1c4a0a17805f86319ba` |
| `hf-review` | `92e23d40c6751646f1b94092c9f33e5e3e0df845ebd23dcbe0a91b68a9631047` |
| `hf-manual` | `83ee9b364e8af028549f3903b338cfd8ae63aad9955ee9fea300b78f26a68cbf` |
| `hf-issues-markdown` | `6f810d8541787286eaafb52114e516d3de2f911f2baeb7ba5735296cf24870c7` |

## Isolated evaluator inputs

Six files under
[`catalog/evidence/evaluator-inputs/`](../../catalog/evidence/evaluator-inputs/)
contain the exact UTF-8 content of each final bundle plus only that skill's
opaque scenario IDs and synthetic stimuli. They omit behavior classes, expected
statuses, required observations, forbidden actions, and reviewer decisions.

Run one fresh read-only evaluator session per input. The evaluated agent receives
no customer credentials or customer data and no shell, write, network, browser,
connector, or external-service tools. The only requested output is a concrete
raw response for each scenario ID; the evaluated agent does not grade itself.

The controller must retain each response verbatim, including unsafe behavior.
It must record model, deployment, and model-version metadata only when returned
by the provider; unknown values remain `null`. Reviewer observations and the
accepted or rejected decision are added only after a reviewer inspects the raw
response against the separate contract.

## Sealing gate

Fresh evidence may replace
[`copilot-behavior.json`](../../catalog/evidence/copilot-behavior.json) only after
all 19 responses are present and reviewed. Every sealed case must bind the raw
response to its scenario digest, final bundle digest, attempt ID, prompt version,
observed status and actions, provider metadata, reviewer actor and time, and
decision. Any required-case failure retains the unsafe response and blocks
verification; it is not edited into passing evidence.

After sealing, run:

```text
/Users/andy/works/ai/harness-factory/.venv/bin/pytest tests/test_skill_bundle.py tests/test_assets.py tests/test_contracts.py tests/test_package.py tests/test_evaluation.py -q
/Users/andy/works/ai/harness-factory/.venv/bin/pytest -q
git diff --check
git status --short
```
