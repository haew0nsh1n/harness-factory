from pathlib import Path

from harness_factory import load_json

from .errors import InterviewModelError
from .schemas import DraftCandidate


class AuthoritativeCatalogService:
    def __init__(self, catalog_root: Path) -> None:
        self._catalog_root = catalog_root

    def load(self) -> dict[str, object]:
        return load_json(self._catalog_root / "catalog.json")


def validate_catalog_references(
    candidate: DraftCandidate, catalog: dict[str, object]
) -> None:
    skills = catalog.get("skills")
    if not isinstance(skills, list):
        raise InterviewModelError(
            "llm_invalid_result", "The approved catalog snapshot is invalid."
        )
    approved_skills: dict[str, tuple[set[str], set[str]]] = {}
    for item in skills:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            raise InterviewModelError(
                "llm_invalid_result", "The approved catalog snapshot is invalid."
            )
        effects = item.get("effects")
        requires = item.get("requires")
        if (
            not isinstance(effects, list)
            or not all(isinstance(value, str) for value in effects)
            or not isinstance(requires, list)
            or not all(isinstance(value, str) for value in requires)
        ):
            raise InterviewModelError(
                "llm_invalid_result", "The approved catalog snapshot is invalid."
            )
        approved_skills[item["id"]] = (set(effects), set(requires))

    declared_tools = {
        f"{system.id}.{capability}"
        for system in candidate.profile.systems
        for capability in system.capabilities
    }
    for step in candidate.workflow.steps:
        skill = approved_skills.get(step.skill)
        if (
            skill is None
            or step.effect not in skill[0]
            or not skill[1].issubset(step.tools)
            or not set(step.tools).issubset(declared_tools)
        ):
            raise InterviewModelError(
                "llm_invalid_result",
                "The model referenced an unapproved catalog capability.",
            )
