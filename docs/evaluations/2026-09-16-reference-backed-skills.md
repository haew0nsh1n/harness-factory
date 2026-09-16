# Reference-backed skill behavior evaluation

Date: 2026-09-16

## Final status

Task 5 evidence is sealed. The production report
[`copilot-behavior.json`](../../catalog/evidence/copilot-behavior.json) now binds
all 19 reviewed scenarios to final bundle digests, attempt IDs, prompt version,
verbatim raw responses, observed status/actions, reviewer decisions, and
provider metadata returned by the evaluator provider.

Provider metadata remained `null` in every wrapper because no model,
deployment, or model-version values were returned.

## Comparison contract

The reviewed scenario contract is
[`skill-quality-scenarios.json`](../../catalog/evidence/skill-quality-scenarios.json).
It contains positive and adversarial coverage for all six skills and all
required behavior classes:

- `success`
- `ambiguous-input`
- `approval-refusal`
- `missing-access`
- `failed-check`
- `resume`
- `uncertain-write`
- `instruction-injection`

The historical source remains
[`skill-quality-baseline.json`](../../catalog/evidence/skill-quality-baseline.json),
which preserves 2026-09-10 observations and explicitly does not prove current
bundle bytes.

## Authoritative bundles

| Skill | Final bundle digest |
| --- | --- |
| `hf-clarify` | `a771b1b913fe59f93d7aef383fb9a1bdff96660a15abe01d43da98c3e9add487` |
| `hf-plan` | `1186e44b843150ce5a189337cec34e31daec797f37f1311dcefcf270eec84126` |
| `hf-tdd` | `d5f40c7c48e86db5426c872f54b02996c98984bb2f20e1c4a0a17805f86319ba` |
| `hf-review` | `92e23d40c6751646f1b94092c9f33e5e3e0df845ebd23dcbe0a91b68a9631047` |
| `hf-manual` | `83ee9b364e8af028549f3903b338cfd8ae63aad9955ee9fea300b78f26a68cbf` |
| `hf-issues-markdown` | `6f810d8541787286eaafb52114e516d3de2f911f2baeb7ba5735296cf24870c7` |

## Refinement history summary

The sealed report retains both review phases:

1. Initial independent review: 18 PASS, 1 FAIL (`sq-clarify-02`) with required
   case failure retained.
2. Corrective `hf-clarify` update + isolated re-evaluation + independent
   re-review: clarify scenarios 5/5 PASS.

No wrapper or review artifact was rewritten to hide the first-pass failure.

## Validation commands

```text
/Users/andy/works/ai/harness-factory/.venv/bin/pytest tests/test_skill_bundle.py tests/test_assets.py tests/test_contracts.py tests/test_package.py tests/test_evaluation.py -q
/Users/andy/works/ai/harness-factory/.venv/bin/pytest -q
git diff --check
git status --short
```
