from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

from harness_factory.contracts import no_symlinks
from harness_factory.delivery import DeliveryMetadata
from harness_factory.errors import HarnessError
from harness_factory.package import MANIFEST, check_package, hash_bytes, inventory
from hf_cli.archive import MAX_ARCHIVE_BYTES, ArchiveError, extract_package
from hf_cli.client import RegistryClient
from hf_cli.errors import CliError


def default_cache_root() -> Path:
    root = os.environ.get("HF_CACHE_DIR") or os.environ.get("XDG_CACHE_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".cache"
    return base / "harness-factory" / "packages"


def _key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cache_entry(cache_root: Path, delivery: DeliveryMetadata) -> Path:
    return (
        cache_root
        / _key(delivery.organization_id)
        / _key(delivery.version_id)
        / delivery.artifact_sha256
    )


def _package_inventory(package: Path) -> dict[str, str]:
    files = inventory(package)
    files[MANIFEST] = hash_bytes((package / MANIFEST).read_bytes())
    return dict(sorted(files.items()))


def _marker(delivery: DeliveryMetadata, package: Path) -> dict[str, object]:
    return {
        "schema_version": 1,
        "delivery": delivery.model_dump(mode="json"),
        "inventory": _package_inventory(package),
    }


def _validate_cached(entry: Path, delivery: DeliveryMetadata) -> Path:
    package = no_symlinks(entry / "package")
    marker_path = no_symlinks(entry / "cache.json")
    try:
        raw = json.loads(marker_path.read_text(encoding="utf-8"))
        if (
            not isinstance(raw, dict)
            or raw.get("schema_version") != 1
            or raw.get("delivery") != delivery.model_dump(mode="json")
            or raw.get("inventory") != _package_inventory(package)
        ):
            raise ValueError
        check_package(package)
        return package
    except (HarnessError, OSError, UnicodeError, ValueError, json.JSONDecodeError):
        raise CliError(
            "cache_corrupted",
            "cached package changed or failed validation; remove this cache entry and preview again",
        ) from None


def _remove_staging(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def materialize_package(
    client: RegistryClient,
    delivery: DeliveryMetadata,
    cache_root: Path,
) -> Path:
    root = Path(cache_root).absolute()
    staging = root / f".staging-{uuid.uuid4().hex}"
    try:
        root = no_symlinks(root)
        if (
            len(delivery.artifact_sha256) != 64
            or any(
                character not in "0123456789abcdef"
                for character in delivery.artifact_sha256
            )
            or delivery.artifact_size < 0
            or delivery.artifact_size > MAX_ARCHIVE_BYTES
        ):
            raise CliError(
                "invalid_delivery",
                "delivery artifact metadata exceeds archive size limit"
                if delivery.artifact_size > MAX_ARCHIVE_BYTES
                else "delivery artifact metadata is invalid",
            )
        entry = no_symlinks(_cache_entry(root, delivery))
        if entry.exists():
            return _validate_cached(entry, delivery)
        staging = no_symlinks(staging)
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        staging.mkdir(mode=0o700)
        archive = staging / "artifact.tar"
        digest, size = client.download_artifact(delivery.version_id, archive)
        if digest != delivery.artifact_sha256 or size != delivery.artifact_size:
            raise CliError(
                "artifact_corrupted",
                "downloaded artifact does not match delivery metadata",
            )
        package = staging / "package"
        extract_package(archive, package)
        check_package(package)
        archive.unlink()
        marker_path = staging / "cache.json"
        marker_path.write_bytes(
            json.dumps(_marker(delivery, package), indent=2, sort_keys=True).encode()
            + b"\n"
        )
        marker_path.chmod(0o600)
        entry.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        for parent in (entry.parent, entry.parent.parent):
            parent.chmod(0o700)
        os.replace(staging, entry)
        return _validate_cached(entry, delivery)
    except CliError:
        raise
    except (ArchiveError, HarnessError, OSError, UnicodeError, ValueError) as exc:
        raise CliError("artifact_invalid", str(exc)) from exc
    finally:
        _remove_staging(staging)
