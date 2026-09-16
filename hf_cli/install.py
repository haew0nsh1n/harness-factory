from __future__ import annotations

import difflib
import hashlib
from pathlib import Path

from harness_factory.delivery import DeliveryMetadata, canonical_json_bytes
from harness_factory.errors import InstallError
from harness_factory.install import apply_install, plan_install
from hf_cli.cache import materialize_package
from hf_cli.client import RegistryClient
from hf_cli.errors import CliError

MAX_DIFF_FILES = 50
MAX_DIFF_BYTES = 64 * 1024
MAX_DIFF_FILE_BYTES = 256 * 1024


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CliError("invalid_response", f"registry returned invalid {field}")
    return value


def _resolve_delivery(
    client: RegistryClient, slug: str, version: str
) -> DeliveryMetadata:
    asset = client.info(slug, version)
    asset_id = _string(asset.get("id"), "asset identity")
    organization_id = _string(
        asset.get("organization_id"), "organization identity"
    )
    if asset.get("slug") != slug:
        raise CliError("identity_mismatch", "registry asset slug does not match request")
    if asset.get("lifecycle") != "active":
        raise CliError("invalid_lifecycle", "registry asset is not active")
    versions = asset.get("versions")
    if not isinstance(versions, list) or len(versions) != 1:
        raise CliError("not_found", "asset version was not found")
    selected = versions[0]
    if not isinstance(selected, dict):
        raise CliError("invalid_response", "registry returned invalid version metadata")
    version_id = _string(selected.get("id"), "version identity")
    if selected.get("version") != version:
        raise CliError("identity_mismatch", "registry version does not match request")
    if selected.get("status") != "published":
        raise CliError("invalid_lifecycle", "registry version is not published")
    manifest_digest = _string(selected.get("digest"), "manifest digest")
    artifact_digest = _string(selected.get("artifact_sha256"), "artifact digest")

    delivery = client.delivery(version_id)
    expected = {
        "organization_id": organization_id,
        "asset_id": asset_id,
        "version_id": version_id,
        "slug": slug,
        "version": version,
    }
    for field, value in expected.items():
        if getattr(delivery, field) != value:
            label = field.removesuffix("_id").replace("_", " ")
            raise CliError(
                "identity_mismatch",
                f"delivery {label} does not match registry metadata",
            )
    actual_manifest_digest = hashlib.sha256(
        canonical_json_bytes(delivery.manifest)
    ).hexdigest()
    if (
        delivery.manifest_sha256 != manifest_digest
        or delivery.manifest_sha256 != actual_manifest_digest
    ):
        raise CliError(
            "digest_mismatch",
            "delivery manifest digest does not match registry metadata",
        )
    if delivery.artifact_sha256 != artifact_digest:
        raise CliError(
            "digest_mismatch",
            "delivery artifact digest does not match registry metadata",
        )
    manifest_asset = delivery.manifest.get("asset")
    manifest_artifact = delivery.manifest.get("artifact")
    if (
        not isinstance(manifest_asset, dict)
        or manifest_asset.get("slug") != slug
        or delivery.manifest.get("version") != version
        or not isinstance(manifest_artifact, dict)
        or manifest_artifact.get("sha256") != delivery.artifact_sha256
    ):
        raise CliError(
            "identity_mismatch",
            "delivery manifest identity does not match requested artifact",
        )
    return delivery


def _text_diff(package: Path, target: Path, files: list[object]) -> list[dict[str, str]]:
    diffs: list[dict[str, str]] = []
    remaining = MAX_DIFF_BYTES
    for item in files:
        if len(diffs) >= MAX_DIFF_FILES or remaining <= 0:
            break
        if not isinstance(item, dict) or item.get("action") != "replace":
            continue
        relative = item.get("path")
        if not isinstance(relative, str):
            continue
        source = package / relative
        destination = target / relative
        try:
            if (
                not source.is_file()
                or not destination.is_file()
                or source.stat().st_size > MAX_DIFF_FILE_BYTES
                or destination.stat().st_size > MAX_DIFF_FILE_BYTES
            ):
                continue
            old = destination.read_text(encoding="utf-8").splitlines(keepends=True)
            new = source.read_text(encoding="utf-8").splitlines(keepends=True)
        except UnicodeError:
            continue
        except OSError:
            raise CliError(
                "diff_failed",
                "unable to read local files for install preview",
            ) from None
        text = "".join(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"target/{relative}",
                tofile=f"package/{relative}",
            )
        )
        if not text:
            continue
        encoded = text.encode("utf-8")
        clipped_bytes = encoded[:remaining]
        try:
            clipped = clipped_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            clipped = clipped_bytes[: exc.start].decode("utf-8")
        diffs.append({"path": relative, "diff": clipped})
        remaining -= len(clipped.encode("utf-8"))
    return diffs


def install_workflow(
    client: RegistryClient,
    slug: str,
    version: str,
    target: Path,
    cache_root: Path,
    approved_digest: str | None,
) -> dict[str, object]:
    delivery = _resolve_delivery(client, slug, version)
    package = materialize_package(client, delivery, cache_root)
    try:
        if approved_digest is None:
            preview = plan_install(package, target)
            preview["diffs"] = _text_diff(
                package,
                Path(str(preview["target"])),
                list(preview["files"]),
            )
            return preview
        return apply_install(package, target, approved_digest)
    except InstallError as exc:
        raise CliError("install_failed", str(exc)) from exc
