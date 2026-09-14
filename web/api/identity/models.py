from dataclasses import dataclass
from typing import FrozenSet

ROLES = frozenset(
    {"author", "reviewer", "registry-admin", "developer", "org-admin"}
)


@dataclass(frozen=True)
class Actor:
    organization_id: str
    subject_id: str
    roles: FrozenSet[str]
