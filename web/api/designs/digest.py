import hashlib
import json


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_design_bytes(
    profile: dict[str, object],
    workflow: dict[str, object],
    scenarios: dict[str, object],
    catalog: dict[str, object],
) -> bytes:
    payload = {
        "schema_version": 1,
        "profile": profile,
        "workflow": workflow,
        "scenarios": scenarios,
        "catalog": catalog,
    }
    return canonical_json_bytes(payload)


def design_digest(
    profile: dict[str, object],
    workflow: dict[str, object],
    scenarios: dict[str, object],
    catalog: dict[str, object],
) -> str:
    return hashlib.sha256(
        canonical_design_bytes(profile, workflow, scenarios, catalog)
    ).hexdigest()
