from __future__ import annotations

import hashlib
import io
import tarfile
from pathlib import Path

import httpx
import pytest

from harness_factory.delivery import DeliveryMetadata
from harness_factory.package import generate_package
from hf_cli.client import RegistryClient
from hf_cli.config import RegistryConfig
from hf_cli.errors import CliError
from fixtures import FixtureCase


class FakeAuth:
    def headers(self) -> dict[str, str]:
        return {"Authorization": "******"}


def registry_config() -> RegistryConfig:
    return RegistryConfig(
        url="https://registry.example.test",
        tenant_id="tenant-1",
        client_id="client-1",
        scope="api://registry/access",
    )


def generated_tar(tmp_path: Path) -> tuple[bytes, dict[str, object]]:
    case = FixtureCase()
    case.setUp()
    try:
        package = tmp_path / "generated"
        generate_package(
            case.profile,
            case.workflow,
            case.scenarios,
            case.catalog,
            case.root,
            package,
        )
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            for path in sorted(package.rglob("*")):
                archive.add(
                    path,
                    arcname=path.relative_to(package).as_posix(),
                    recursive=False,
                )
        return buffer.getvalue(), {}
    finally:
        case.doCleanups()


def delivery_for(payload: bytes, manifest: dict[str, object]) -> DeliveryMetadata:
    manifest = {
        "schema_version": 1,
        "asset": {"type": "workflow", "slug": "issue-flow"},
        "version": "1.0.0",
        "runtime": "copilot-cli",
        "design_digest": "d" * 64,
        "artifact": {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "key": "private/artifact.tar",
        },
        "dependencies": [],
    }
    canonical = __import__("json").dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    return DeliveryMetadata(
        schema_version=1,
        organization_id="org-acme",
        asset_id="asset-1",
        version_id="version-1",
        slug="issue-flow",
        version="1.0.0",
        manifest=manifest,
        manifest_sha256=hashlib.sha256(canonical).hexdigest(),
        artifact_sha256=hashlib.sha256(payload).hexdigest(),
        artifact_size=len(payload),
    )


class DownloadingClient:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls = 0

    def download_artifact(self, version_id: str, destination: Path) -> tuple[str, int]:
        assert version_id == "version-1"
        self.calls += 1
        destination.write_bytes(self.payload)
        return hashlib.sha256(self.payload).hexdigest(), len(self.payload)


def test_registry_download_enforces_stream_limit_without_trusting_content_length(
    tmp_path: Path, monkeypatch
) -> None:
    from hf_cli import client as client_module

    monkeypatch.setattr(client_module, "MAX_ARCHIVE_BYTES", 3)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Length": "2"}, content=b"1234")

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = RegistryClient(registry_config(), FakeAuth(), http_client=http)
    destination = tmp_path / "download.tar"

    with pytest.raises(CliError, match="size limit") as error:
        client.download_artifact("version-1", destination)

    assert error.value.code == "artifact_too_large"
    assert not destination.exists()


def test_registry_download_accepts_exact_limit_and_rejects_declared_oversize(
    tmp_path: Path, monkeypatch
) -> None:
    from hf_cli import client as client_module

    monkeypatch.setattr(client_module, "MAX_ARCHIVE_BYTES", 3)
    responses = iter(
        [
            httpx.Response(200, content=b"123"),
            httpx.Response(200, headers={"Content-Length": "4"}, content=b""),
        ]
    )
    client = RegistryClient(
        registry_config(),
        FakeAuth(),
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: next(responses))
        ),
    )

    assert client.download_artifact("version-1", tmp_path / "exact.tar") == (
        hashlib.sha256(b"123").hexdigest(),
        3,
    )
    with pytest.raises(CliError) as error:
        client.download_artifact("version-1", tmp_path / "large.tar")
    assert error.value.code == "artifact_too_large"
    assert not (tmp_path / "large.tar").exists()


def test_materialize_uses_private_stable_verified_cache(
    tmp_path: Path,
) -> None:
    from hf_cli.cache import materialize_package

    payload, manifest = generated_tar(tmp_path)
    delivery = delivery_for(payload, manifest)
    client = DownloadingClient(payload)
    cache_root = tmp_path / "cache"

    first = materialize_package(client, delivery, cache_root)
    second = materialize_package(client, delivery, cache_root)

    assert first == second
    assert client.calls == 1
    assert first.is_dir()
    assert first.stat().st_mode & 0o777 == 0o700
    assert delivery.organization_id not in first.parts
    assert delivery.version_id not in first.parts


@pytest.mark.parametrize("field", ["artifact_sha256", "artifact_size"])
def test_materialize_rejects_download_bytes_not_bound_to_metadata(
    tmp_path: Path, field: str
) -> None:
    from hf_cli.cache import materialize_package

    payload, manifest = generated_tar(tmp_path)
    delivery = delivery_for(payload, manifest)
    replacement = {"artifact_sha256": "0" * 64, "artifact_size": len(payload) + 1}
    delivery = DeliveryMetadata(
        **{**delivery.model_dump(), field: replacement[field]}
    )

    with pytest.raises(CliError, match="metadata"):
        materialize_package(DownloadingClient(payload), delivery, tmp_path / "cache")

    assert not list((tmp_path / "cache").rglob(".staging-*"))


def test_materialize_rejects_metadata_over_archive_limit_without_downloading(
    tmp_path: Path,
) -> None:
    from harness_factory.archive import MAX_ARCHIVE_BYTES
    from hf_cli.cache import materialize_package

    payload, manifest = generated_tar(tmp_path)
    delivery = delivery_for(payload, manifest)
    delivery = DeliveryMetadata(
        **{**delivery.model_dump(), "artifact_size": MAX_ARCHIVE_BYTES + 1}
    )
    client = DownloadingClient(payload)

    with pytest.raises(CliError, match="size limit"):
        materialize_package(client, delivery, tmp_path / "cache")

    assert client.calls == 0


def test_materialize_rehashes_cached_inventory_and_rejects_changed_bytes(
    tmp_path: Path,
) -> None:
    from hf_cli.cache import materialize_package

    payload, manifest = generated_tar(tmp_path)
    delivery = delivery_for(payload, manifest)
    client = DownloadingClient(payload)
    package = materialize_package(client, delivery, tmp_path / "cache")
    changed = package / ".agents/skills/worker/SKILL.md"
    changed.write_text(changed.read_text() + "\ntampered\n")

    with pytest.raises(CliError, match="cached package"):
        materialize_package(client, delivery, tmp_path / "cache")

    assert client.calls == 1


def test_materialize_rejects_symlinked_cache_ancestor_without_touching_target(
    tmp_path: Path,
) -> None:
    from hf_cli.cache import materialize_package

    payload, manifest = generated_tar(tmp_path)
    delivery = delivery_for(payload, manifest)
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "cache"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(CliError, match="symlink"):
        materialize_package(DownloadingClient(payload), delivery, link)

    assert not list(real.iterdir())


def test_failed_staging_cleanup_preserves_unrelated_cache_entries(
    tmp_path: Path,
) -> None:
    from hf_cli.cache import materialize_package

    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    unrelated = cache_root / "customer.keep"
    unrelated.write_text("keep")
    payload = b"not a tar"
    delivery = delivery_for(payload, {"schema_version": 1})

    with pytest.raises(CliError):
        materialize_package(DownloadingClient(payload), delivery, cache_root)

    assert unrelated.read_text() == "keep"
    assert not list(cache_root.rglob(".staging-*"))
