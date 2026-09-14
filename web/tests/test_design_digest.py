from copy import deepcopy
from pathlib import Path

from harness_factory import load_json
from web.api.designs.digest import design_digest


FIXTURE_ROOT = Path(__file__).resolve().parents[2]


def load_design_fixture(name: str) -> dict[str, object]:
    if name == "catalog":
        return load_json(FIXTURE_ROOT / "catalog" / "catalog.json")
    return load_json(FIXTURE_ROOT / "examples" / "github-issue" / f"{name}.json")


def test_design_digest_is_stable_for_reordered_profile_keys():
    profile = load_design_fixture("profile")
    workflow = load_design_fixture("workflow")
    scenarios = load_design_fixture("scenarios")
    catalog = load_design_fixture("catalog")

    first = design_digest(profile, workflow, scenarios, catalog)
    second = design_digest(
        dict(reversed(list(profile.items()))), workflow, scenarios, catalog
    )

    assert first == second
    assert len(first) == 64


def test_design_digest_changes_when_workflow_completion_changes():
    profile = load_design_fixture("profile")
    workflow = load_design_fixture("workflow")
    scenarios = load_design_fixture("scenarios")
    catalog = load_design_fixture("catalog")
    changed_workflow = deepcopy(workflow)
    changed_workflow["steps"][0]["completion"] = "Different completion criteria."

    assert (
        design_digest(profile, workflow, scenarios, catalog)
        != design_digest(profile, changed_workflow, scenarios, catalog)
    )
