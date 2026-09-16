import hashlib
import re
from collections.abc import Mapping
from pathlib import Path

from .contracts import identifier, load_json, no_symlinks, relative_path, require, shape
from .delivery import canonical_json_bytes

MANIFEST_NAME = "bundle.json"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def _reject_cache_resource(path: str) -> None:
    require(
        "__pycache__" not in path.split("/") and not path.endswith(".pyc"),
        f"skill bundle: invalid cache resource: {path}",
    )


def skill_resource_hashes(skill_root: Path) -> dict[str, str]:
    root = no_symlinks(skill_root).resolve()
    require(root.is_dir(), "skill bundle: expected directory")
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        checked = no_symlinks(path)
        relative = checked.relative_to(root).as_posix()
        _reject_cache_resource(relative)
        require(checked.is_file() or checked.is_dir(), "skill bundle: unsupported entry")
        if checked.is_file() and checked != root / MANIFEST_NAME:
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


def validate_skill_bundle(skill_root: Path, skill_id: str) -> dict[str, object]:
    root = no_symlinks(skill_root).resolve()
    manifest = load_json(root / MANIFEST_NAME)
    shape(manifest, "schema_version skill_id resources digest", "skill bundle")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 2,
            "skill bundle.schema_version: expected 2")
    identifier(manifest["skill_id"], "skill bundle.skill_id")
    require(manifest["skill_id"] == skill_id, "skill bundle.skill_id: does not match catalog skill")
    require(isinstance(manifest["resources"], dict), "skill bundle.resources: expected hash map")
    for path, digest in manifest["resources"].items():
        relative_path(root, path, "skill bundle.resources")
        _reject_cache_resource(path)
        require(isinstance(digest, str) and SHA256.fullmatch(digest) is not None,
                "skill bundle.resources: invalid SHA-256 hash")
    require(isinstance(manifest["digest"], str) and SHA256.fullmatch(manifest["digest"]) is not None,
            "skill bundle.digest: invalid SHA-256 hash")

    resources = manifest["resources"]
    actual = skill_resource_hashes(root)
    require(resources == actual, "skill bundle: resource hash mismatch")
    require(manifest["digest"] == skill_bundle_digest(skill_id, resources),
            "skill bundle: bundle digest mismatch")
    return manifest
