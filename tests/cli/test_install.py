from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from harness_factory.delivery import DeliveryMetadata
from harness_factory.package import generate_package
from hf_cli.errors import CliError
from fixtures import FixtureCase


def generated_delivery(tmp_path: Path) -> tuple[bytes, DeliveryMetadata]:
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
        payload = buffer.getvalue()
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
        canonical = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        return payload, DeliveryMetadata(
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
    finally:
        case.doCleanups()


class Registry:
    def __init__(self, payload: bytes, delivery: DeliveryMetadata) -> None:
        self.payload = payload
        self.registry_metadata = delivery
        self.metadata = [delivery, delivery]
        self.info_calls = 0
        self.delivery_calls = 0
        self.download_calls = 0

    def info(self, slug: str, version: str) -> dict[str, object]:
        self.info_calls += 1
        metadata = self.registry_metadata
        return {
            "id": metadata.asset_id,
            "organization_id": metadata.organization_id,
            "slug": slug,
            "lifecycle": "active",
            "versions": [
                {
                    "id": metadata.version_id,
                    "version": version,
                    "digest": metadata.manifest_sha256,
                    "status": "published",
                    "artifact_sha256": metadata.artifact_sha256,
                }
            ],
        }

    def delivery(self, version_id: str) -> DeliveryMetadata:
        metadata = self.metadata[
            min(self.delivery_calls, len(self.metadata) - 1)
        ]
        self.delivery_calls += 1
        return metadata

    def download_artifact(self, version_id: str, destination: Path) -> tuple[str, int]:
        self.download_calls += 1
        destination.write_bytes(self.payload)
        return hashlib.sha256(self.payload).hexdigest(), len(self.payload)


def test_preview_and_apply_use_same_stable_source_and_preserve_customer_files(
    tmp_path: Path,
) -> None:
    from hf_cli.install import install_workflow

    payload, delivery = generated_delivery(tmp_path)
    client = Registry(payload, delivery)
    target = tmp_path / "customer"
    target.mkdir()
    (target / "customer.py").write_text("customer = True\n")
    cache = tmp_path / "cache"

    preview = install_workflow(
        client, "issue-flow", "1.0.0", target, cache, None
    )
    assert preview["operation"] == "install-preview"
    assert not (target / ".harness").exists()
    result = install_workflow(
        client,
        "issue-flow",
        "1.0.0",
        target,
        cache,
        str(preview["digest"]),
    )

    assert result["operation"] == "install"
    assert result["digest"] == preview["digest"]
    assert result["target"] == preview["target"]
    assert (target / "customer.py").read_text() == "customer = True\n"
    assert client.info_calls == 2
    assert client.delivery_calls == 2
    assert client.download_calls == 1


def test_preview_adds_bounded_local_text_diff_without_changing_digest(
    tmp_path: Path, monkeypatch
) -> None:
    from harness_factory.install import plan_install
    from hf_cli import install as install_module

    payload, delivery = generated_delivery(tmp_path)
    client = Registry(payload, delivery)
    target = tmp_path / "customer"
    managed = target / "INSTALL.md"
    managed.parent.mkdir()
    managed.write_text("customer instructions\n")
    monkeypatch.setattr(install_module, "MAX_DIFF_BYTES", 120)

    preview = install_module.install_workflow(
        client, "issue-flow", "1.0.0", target, tmp_path / "cache", None
    )
    core = plan_install(Path(str(preview["package"])), target)

    assert preview["digest"] == core["digest"]
    assert preview["diffs"]
    assert len(json.dumps(preview["diffs"])) < 300
    assert "customer instructions" in preview["diffs"][0]["diff"]
    assert managed.read_text() == "customer instructions\n"


def test_preview_diff_limit_is_utf8_bytes_for_korean_text(
    tmp_path: Path, monkeypatch
) -> None:
    from hf_cli import install as install_module

    payload, delivery = generated_delivery(tmp_path)
    client = Registry(payload, delivery)
    target = tmp_path / "customer"
    managed = target / "INSTALL.md"
    managed.parent.mkdir()
    managed.write_text("기존 고객 지침\n" * 100, encoding="utf-8")
    monkeypatch.setattr(install_module, "MAX_DIFF_BYTES", 256)

    preview = install_module.install_workflow(
        client, "issue-flow", "1.0.0", target, tmp_path / "cache", None
    )

    assert preview["diffs"]
    diff = preview["diffs"][0]["diff"]
    assert len(diff.encode("utf-8")) <= 256
    assert diff.encode("utf-8").decode("utf-8") == diff


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"organization_id": "other-org"}, "organization"),
        ({"asset_id": "other-asset"}, "asset"),
        ({"version_id": "other-version"}, "version"),
        ({"slug": "other-flow"}, "slug"),
        ({"version": "2.0.0"}, "version"),
        ({"manifest_sha256": "0" * 64}, "manifest"),
        ({"artifact_sha256": "0" * 64}, "artifact"),
    ],
)
def test_install_rejects_delivery_identity_or_digest_mismatch(
    tmp_path: Path, mutation: dict[str, object], message: str
) -> None:
    from hf_cli.install import install_workflow

    payload, delivery = generated_delivery(tmp_path)
    bad = DeliveryMetadata(**{**delivery.model_dump(), **mutation})
    client = Registry(payload, delivery)
    client.metadata = [bad]

    with pytest.raises(CliError, match=message):
        install_workflow(
            client,
            "issue-flow",
            "1.0.0",
            tmp_path / "target",
            tmp_path / "cache",
            None,
        )

    assert not (tmp_path / "target").exists()


def test_apply_requires_fresh_published_active_registry_lifecycle(
    tmp_path: Path,
) -> None:
    from hf_cli.install import install_workflow

    payload, delivery = generated_delivery(tmp_path)
    client = Registry(payload, delivery)
    target = tmp_path / "target"
    preview = install_workflow(
        client, "issue-flow", "1.0.0", target, tmp_path / "cache", None
    )
    original_info = client.info

    def revoked_info(slug: str, version: str) -> dict[str, object]:
        value = original_info(slug, version)
        value["versions"][0]["status"] = "revoked"
        return value

    client.info = revoked_info  # type: ignore[method-assign]
    with pytest.raises(CliError, match="published"):
        install_workflow(
            client,
            "issue-flow",
            "1.0.0",
            target,
            tmp_path / "cache",
            str(preview["digest"]),
        )

    assert not target.exists()


def test_apply_rejects_fresh_metadata_change_and_cached_source_change(
    tmp_path: Path,
) -> None:
    from hf_cli.install import install_workflow

    payload, delivery = generated_delivery(tmp_path)
    client = Registry(payload, delivery)
    cache = tmp_path / "cache"
    target = tmp_path / "target"
    preview = install_workflow(
        client, "issue-flow", "1.0.0", target, cache, None
    )
    changed = DeliveryMetadata(
        **{**delivery.model_dump(), "artifact_sha256": "f" * 64}
    )
    client.metadata = [delivery, changed]
    with pytest.raises(CliError, match="artifact"):
        install_workflow(
            client,
            "issue-flow",
            "1.0.0",
            target,
            cache,
            str(preview["digest"]),
        )
    assert not target.exists()

    client.metadata = [delivery, delivery]
    package = Path(str(preview["package"]))
    source = package / ".agents/skills/worker/SKILL.md"
    source.write_text(source.read_text() + "\ntampered\n")
    with pytest.raises(CliError, match="cached package"):
        install_workflow(
            client,
            "issue-flow",
            "1.0.0",
            target,
            cache,
            str(preview["digest"]),
        )
    assert not target.exists()


def test_apply_preserves_core_stale_target_and_partial_write_semantics(
    tmp_path: Path,
) -> None:
    from hf_cli.install import install_workflow

    payload, delivery = generated_delivery(tmp_path)
    client = Registry(payload, delivery)
    cache = tmp_path / "cache"
    target = tmp_path / "target"
    preview = install_workflow(
        client, "issue-flow", "1.0.0", target, cache, None
    )
    target.mkdir()
    (target / "INSTALL.md").write_text("changed after preview\n")

    with pytest.raises(
        CliError, match="stale|incorrect|state changed"
    ) as error:
        install_workflow(
            client,
            "issue-flow",
            "1.0.0",
            target,
            cache,
            str(preview["digest"]),
        )

    assert error.value.code == "install_failed"
    assert not (target / ".harness").exists()


def test_cli_install_passes_preview_or_approval_to_workflow(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from hf_cli import main as cli_main

    calls: list[tuple[object, ...]] = []
    config = object()
    auth = object()
    client = object()
    monkeypatch.setattr(cli_main, "load_config", lambda **kwargs: (config, None))
    monkeypatch.setattr(cli_main, "AuthSession", lambda *args, **kwargs: auth)
    monkeypatch.setattr(cli_main, "RegistryClient", lambda *args: client)
    monkeypatch.setattr(cli_main, "default_cache_root", lambda: tmp_path / "cache")
    monkeypatch.setattr(
        cli_main,
        "install_workflow",
        lambda *args: calls.append(args)
        or {"ok": True, "operation": "install-preview", "digest": "a" * 64},
    )

    assert (
        cli_main.run(
            [
                "install",
                "issue-flow@1.0.0",
                "--target",
                str(tmp_path / "target"),
                "--json",
            ]
        )
        == 0
    )
    assert calls[-1][-1] is None
    assert json.loads(capsys.readouterr().out)["result"]["operation"] == (
        "install-preview"
    )

    assert (
        cli_main.run(
            [
                "install",
                "issue-flow@1.0.0",
                "--target",
                str(tmp_path / "target"),
                "--approve",
                "b" * 64,
                "--json",
            ]
        )
        == 0
    )
    assert calls[-1][-1] == "b" * 64
