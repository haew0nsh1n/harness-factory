from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class DeliveryMetadata:
    schema_version: int
    organization_id: str
    asset_id: str
    version_id: str
    slug: str
    version: str
    manifest: dict[str, Any]
    manifest_sha256: str
    artifact_sha256: str
    artifact_size: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> DeliveryMetadata:
        required_strings = (
            "organization_id",
            "asset_id",
            "version_id",
            "slug",
            "version",
            "manifest_sha256",
            "artifact_sha256",
        )
        if value.get("schema_version") != 1:
            raise ValueError("unsupported delivery metadata schema")
        if any(not isinstance(value.get(field), str) for field in required_strings):
            raise ValueError("invalid delivery metadata")
        manifest = value.get("manifest")
        artifact_size = value.get("artifact_size")
        if (
            not isinstance(manifest, dict)
            or not isinstance(artifact_size, int)
            or isinstance(artifact_size, bool)
        ):
            raise ValueError("invalid delivery metadata")
        return cls(
            schema_version=1,
            organization_id=value["organization_id"],
            asset_id=value["asset_id"],
            version_id=value["version_id"],
            slug=value["slug"],
            version=value["version"],
            manifest=manifest,
            manifest_sha256=value["manifest_sha256"],
            artifact_sha256=value["artifact_sha256"],
            artifact_size=artifact_size,
        )

    def model_dump(self, *, mode: str = "python") -> dict[str, Any]:
        if mode not in {"python", "json"}:
            raise ValueError("unsupported serialization mode")
        return asdict(self)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
