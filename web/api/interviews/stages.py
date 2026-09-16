from collections.abc import Iterable


SELECTABLE_STAGES = (
    "discovery",
    "planning",
    "implementation",
    "testing",
    "review",
    "release",
    "operations",
)
SELECTABLE_STAGE_SET = frozenset(SELECTABLE_STAGES)


def canonical_stages(stages: Iterable[str] | None) -> tuple[str, ...]:
    if stages is None:
        return SELECTABLE_STAGES
    selected = frozenset(stages)
    return tuple(stage for stage in SELECTABLE_STAGES if stage in selected)


def stored_stages(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return SELECTABLE_STAGES
    stages = [str(stage) for stage in value]
    if not stages or len(stages) != len(set(stages)):
        return SELECTABLE_STAGES
    if any(stage not in SELECTABLE_STAGE_SET for stage in stages):
        return SELECTABLE_STAGES
    return canonical_stages(stages)
