import hashlib
import json
from pathlib import Path

import pytest

from harness_factory.errors import ValidationError
from harness_factory.skill_bundle import (
    skill_bundle_digest,
    skill_resource_hashes,
    validate_skill_bundle,
)


def make_bundle(tmp_path: Path, skill_id: str = "worker") -> Path:
    skill = tmp_path / "skill"
    (skill / "references").mkdir(parents=True)
    (skill / "templates").mkdir()
    (skill / "SKILL.md").write_text("entry\n")
    (skill / "references" / "guide.md").write_text("guide\n")
    (skill / "templates" / "report.md").write_text("report\n")
    resources = {
        "SKILL.md": hashlib.sha256(b"entry\n").hexdigest(),
        "references/guide.md": hashlib.sha256(b"guide\n").hexdigest(),
        "templates/report.md": hashlib.sha256(b"report\n").hexdigest(),
    }
    payload = {
        "schema_version": 2,
        "skill_id": skill_id,
        "resources": resources,
    }
    manifest = {
        **payload,
        "digest": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    (skill / "bundle.json").write_text(json.dumps(manifest))
    return skill


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


def test_skill_resource_hashes_exclude_only_the_manifest(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path)
    (skill / "NOTICE").write_text("notice\n")

    assert set(skill_resource_hashes(skill)) == {
        "NOTICE",
        "SKILL.md",
        "references/guide.md",
        "templates/report.md",
    }


def test_skill_resource_hashes_include_nested_bundle_named_resources(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path)
    nested_manifest = skill / "references" / "bundle.json"
    nested_manifest.write_text("nested resource\n")

    hashes = skill_resource_hashes(skill)

    assert hashes["references/bundle.json"] == hashlib.sha256(
        b"nested resource\n"
    ).hexdigest()


def test_skill_bundle_digest_is_canonical_across_resource_mapping_order() -> None:
    resources = {
        "templates/report.md": "c" * 64,
        "SKILL.md": "a" * 64,
        "references/guide.md": "b" * 64,
    }

    assert skill_bundle_digest("worker", resources) == (
        "86e7102e7a3428525877e06f6ed049463b1535297c29b1b4c5b252fcef3bac2f"
    )


def test_validate_skill_bundle_returns_valid_manifest(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path, "worker")

    bundle = validate_skill_bundle(skill, "worker")

    assert bundle["skill_id"] == "worker"
    assert bundle["resources"] == {
        "SKILL.md": hashlib.sha256(b"entry\n").hexdigest(),
        "references/guide.md": hashlib.sha256(b"guide\n").hexdigest(),
        "templates/report.md": hashlib.sha256(b"report\n").hexdigest(),
    }


def test_validate_skill_bundle_rejects_changed_reference(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path, "worker")
    (skill / "references" / "guide.md").write_text("changed\n")

    with pytest.raises(ValidationError, match="resource hash mismatch"):
        validate_skill_bundle(skill, "worker")


def test_validate_skill_bundle_rejects_unlisted_resource(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path)
    (skill / "references" / "unlisted.md").write_text("unlisted\n")

    with pytest.raises(ValidationError, match="resource hash mismatch"):
        validate_skill_bundle(skill, "worker")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("skill_id", "other", "skill_id"),
        ("resources", {"../escape.md": "a" * 64}, "unsafe relative path"),
        ("resources", {"SKILL.md": "A" * 64}, "invalid SHA-256 hash"),
    ],
)
def test_validate_skill_bundle_rejects_invalid_manifest_values(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    skill = make_bundle(tmp_path)
    manifest_path = skill / "bundle.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValidationError, match=message):
        validate_skill_bundle(skill, "worker")


def test_validate_skill_bundle_rejects_digest_for_different_resources(tmp_path: Path) -> None:
    skill = make_bundle(tmp_path)
    manifest_path = skill / "bundle.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["digest"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValidationError, match="bundle digest mismatch"):
        validate_skill_bundle(skill, "worker")
