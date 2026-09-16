from __future__ import annotations

import asyncio
import hashlib
import io
import tarfile

import pytest
from sqlalchemy.orm import Session
from starlette.requests import ClientDisconnect

from web.api.designs.digest import canonical_json_bytes
from web.api.distribution.routes import download_artifact
from web.api.distribution.schemas import DeliveryMetadata
from web.api.distribution.service import PreparedDelivery
from web.api.identity.models import Actor
from web.api.registry.models import AssetVersion
from web.tests.test_registry_api import (
    approve_version,
    build_headers,
    create_asset,
    create_version,
    publish_version,
    registry_client,
    seed_built_design,
)


def build_tar_bytes(files: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, content in (files or {"README.md": b"workflow package\n"}).items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


def create_published_distribution(
    client,
    *,
    slug: str = "delivery-workflow",
    design_id: str = "design-delivery",
    version: str = "1.2.3",
    artifact_bytes: bytes | None = None,
) -> tuple[dict[str, object], dict[str, str], bytes]:
    artifact_bytes = artifact_bytes or build_tar_bytes()
    asset = create_asset(client, slug=slug)
    seeded = seed_built_design(
        client,
        design_id=design_id,
        artifact_bytes=artifact_bytes,
    )
    created = create_version(client, asset["id"], seeded, version=version)
    assert created.status_code == 201, created.text
    asset_version = created.json()["version"]
    assert (
        approve_version(client, asset_version["id"], asset_version["digest"]).status_code
        == 200
    )
    published = publish_version(
        client,
        asset_version["id"],
        asset_version["digest"],
    )
    assert published.status_code == 200, published.text
    return asset, published.json()["version"], artifact_bytes


@pytest.mark.parametrize("roles", ["developer", "org-admin"])
def test_published_delivery_metadata_binds_tenant_manifest_and_artifact(
    registry_client,
    roles: str,
) -> None:
    asset, version, artifact_bytes = create_published_distribution(
        registry_client,
        slug=f"delivery-{roles}",
        design_id=f"design-delivery-{roles}",
    )

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/delivery",
        headers=build_headers(subject_id="consumer-1", roles=roles),
    )

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "delivery": {
            "schema_version": 1,
            "organization_id": "org-acme",
            "asset_id": asset["id"],
            "version_id": version["id"],
            "slug": asset["slug"],
            "version": version["version"],
            "manifest": version["manifest"],
            "manifest_sha256": hashlib.sha256(
                canonical_json_bytes(version["manifest"])
            ).hexdigest(),
            "artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            "artifact_size": len(artifact_bytes),
        },
    }


def test_artifact_download_streams_only_the_validated_published_tar(
    registry_client,
) -> None:
    asset, version, artifact_bytes = create_published_distribution(registry_client)

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/artifact",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 200
    assert response.content == artifact_bytes
    assert response.headers["content-type"] == "application/x-tar"
    assert response.headers["content-length"] == str(len(artifact_bytes))
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{asset["slug"]}-{version["version"]}.tar"'
    )


@pytest.mark.parametrize("endpoint", ["delivery", "artifact"])
def test_delivery_endpoints_hide_other_tenants_and_unpublished_versions(
    registry_client,
    endpoint: str,
) -> None:
    _, published, _ = create_published_distribution(registry_client)
    draft_asset = create_asset(registry_client, slug="draft-delivery")
    draft_build = seed_built_design(
        registry_client,
        design_id="design-draft-delivery",
        artifact_bytes=build_tar_bytes(),
    )
    draft_response = create_version(
        registry_client,
        draft_asset["id"],
        draft_build,
        version="2.0.0",
    )
    assert draft_response.status_code == 201
    draft = draft_response.json()["version"]

    other_tenant = registry_client.get(
        f"/api/registry/versions/{published['id']}/{endpoint}",
        headers=build_headers(
            organization_id="org-umbrella",
            subject_id="consumer-2",
            roles="developer",
        ),
    )
    unpublished = registry_client.get(
        f"/api/registry/versions/{draft['id']}/{endpoint}",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert other_tenant.status_code == 404
    assert other_tenant.json() == {
        "ok": False,
        "error": "version not found",
        "code": "error",
    }
    assert unpublished.status_code == 404


@pytest.mark.parametrize("endpoint", ["delivery", "artifact"])
def test_delivery_endpoints_require_developer_or_org_admin(
    registry_client,
    endpoint: str,
) -> None:
    _, version, _ = create_published_distribution(registry_client)

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/{endpoint}",
        headers=build_headers(subject_id="author-1", roles="author"),
    )

    assert response.status_code == 403
    assert response.json() == {
        "ok": False,
        "error": "required role missing",
        "code": "forbidden",
    }


def test_revoke_after_metadata_blocks_artifact_download(registry_client) -> None:
    _, version, _ = create_published_distribution(registry_client)
    headers = build_headers(subject_id="developer-1", roles="developer")
    metadata = registry_client.get(
        f"/api/registry/versions/{version['id']}/delivery",
        headers=headers,
    )
    assert metadata.status_code == 200

    revoked = registry_client.post(
        f"/api/registry/versions/{version['id']}/revoke",
        headers=build_headers(subject_id="admin-1", roles="registry-admin"),
        json={"expected_digest": version["digest"]},
    )
    assert revoked.status_code == 200

    download = registry_client.get(
        f"/api/registry/versions/{version['id']}/artifact",
        headers=headers,
    )

    assert download.status_code == 404


@pytest.mark.parametrize(
    ("mode", "expected_code"),
    [
        ("missing", "artifact_unavailable"),
        ("corrupted", "artifact_corrupted"),
    ],
)
def test_delivery_rejects_missing_or_corrupt_artifact_without_leaking_paths(
    registry_client,
    mode: str,
    expected_code: str,
) -> None:
    _, version, _ = create_published_distribution(
        registry_client,
        slug=f"storage-{mode}",
        design_id=f"design-storage-{mode}",
    )
    artifact_path = (
        registry_client.app.state.settings.artifact_root
        / version["manifest"]["artifact"]["key"]
    )
    if mode == "missing":
        artifact_path.unlink()
    else:
        artifact_path.write_bytes(build_tar_bytes({"changed.txt": b"changed\n"}))

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/artifact",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == expected_code
    assert str(registry_client.app.state.settings.artifact_root) not in response.text
    assert version["manifest"]["artifact"]["key"] not in response.text


def test_delivery_rejects_manifest_digest_corruption(registry_client) -> None:
    _, version, _ = create_published_distribution(registry_client)
    with Session(registry_client.app.state.engine) as session:
        stored = session.get(AssetVersion, version["id"])
        assert stored is not None
        stored.manifest_json = {**stored.manifest_json, "version": "9.9.9"}
        session.commit()

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/delivery",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 422
    assert response.json() == {
        "ok": False,
        "error": "version delivery metadata failed integrity check",
        "code": "artifact_corrupted",
    }


def test_delivery_rejects_artifact_digest_that_differs_from_canonical_manifest(
    registry_client,
) -> None:
    _, version, _ = create_published_distribution(registry_client)
    replacement = build_tar_bytes({"replacement.txt": b"replacement\n"})
    artifact_path = (
        registry_client.app.state.settings.artifact_root
        / version["manifest"]["artifact"]["key"]
    )
    artifact_path.write_bytes(replacement)
    with Session(registry_client.app.state.engine) as session:
        stored = session.get(AssetVersion, version["id"])
        assert stored is not None
        stored.artifact_digest = hashlib.sha256(replacement).hexdigest()
        session.commit()

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/delivery",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_corrupted"


def test_delivery_uses_only_the_stored_artifact_key_and_rejects_unsafe_keys(
    registry_client,
) -> None:
    _, version, _ = create_published_distribution(registry_client)
    with Session(registry_client.app.state.engine) as session:
        stored = session.get(AssetVersion, version["id"])
        assert stored is not None
        stored.artifact_key = "../../outside.tar"
        session.commit()

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/artifact?key=/tmp/attacker.tar",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_corrupted"
    assert "outside.tar" not in response.text
    assert "attacker.tar" not in response.text


def build_special_tar(kind: str) -> bytes:
    buffer = io.BytesIO()
    mode = "w:gz" if kind == "compressed" else "w"
    with tarfile.open(fileobj=buffer, mode=mode) as archive:
        if kind == "absolute":
            member = tarfile.TarInfo("/absolute.txt")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        elif kind == "parent":
            member = tarfile.TarInfo("../parent.txt")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        elif kind == "duplicate":
            for content in (b"a", b"b"):
                member = tarfile.TarInfo("duplicate.txt")
                member.size = 1
                archive.addfile(member, io.BytesIO(content))
        elif kind == "symlink":
            member = tarfile.TarInfo("link")
            member.type = tarfile.SYMTYPE
            member.linkname = "target"
            archive.addfile(member)
        elif kind == "hardlink":
            member = tarfile.TarInfo("link")
            member.type = tarfile.LNKTYPE
            member.linkname = "target"
            archive.addfile(member)
        elif kind == "fifo":
            member = tarfile.TarInfo("pipe")
            member.type = tarfile.FIFOTYPE
            archive.addfile(member)
        elif kind == "device":
            member = tarfile.TarInfo("device")
            member.type = tarfile.CHRTYPE
            archive.addfile(member)
        elif kind == "sparse":
            member = tarfile.TarInfo("sparse.bin")
            member.size = 1
            member.pax_headers = {"GNU.sparse.map": "0,1"}
            archive.addfile(member, io.BytesIO(b"x"))
        elif kind == "compressed":
            member = tarfile.TarInfo("compressed.txt")
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
        else:
            raise AssertionError(f"unsupported test tar kind: {kind}")
    return buffer.getvalue()


@pytest.mark.parametrize(
    "kind",
    [
        "absolute",
        "parent",
        "duplicate",
        "symlink",
        "hardlink",
        "fifo",
        "device",
        "sparse",
        "compressed",
    ],
)
def test_delivery_rejects_unsafe_or_unsupported_tar_members(
    registry_client,
    kind: str,
) -> None:
    _, version, _ = create_published_distribution(
        registry_client,
        slug=f"invalid-{kind}",
        design_id=f"design-invalid-{kind}",
        artifact_bytes=build_special_tar(kind),
    )

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/artifact",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "artifact_invalid"


def test_archive_validator_enforces_all_distribution_bounds(monkeypatch) -> None:
    from web.api.distribution import service as distribution_service

    assert distribution_service.MAX_ARCHIVE_BYTES == 100 * 1024 * 1024
    assert distribution_service.MAX_EXPANDED_BYTES == 256 * 1024 * 1024
    assert distribution_service.MAX_ARCHIVE_ENTRIES == 10_000
    assert distribution_service.MAX_FILE_BYTES == 16 * 1024 * 1024

    monkeypatch.setattr(distribution_service, "MAX_FILE_BYTES", 3)
    with pytest.raises(
        distribution_service.DeliveryArtifactError,
        match="file exceeds size limit",
    ):
        distribution_service.DistributionService._validate_archive(
            io.BytesIO(build_tar_bytes({"large.txt": b"1234"}))
        )

    monkeypatch.setattr(distribution_service, "MAX_FILE_BYTES", 10)
    monkeypatch.setattr(distribution_service, "MAX_EXPANDED_BYTES", 3)
    with pytest.raises(
        distribution_service.DeliveryArtifactError,
        match="expanded size limit",
    ):
        distribution_service.DistributionService._validate_archive(
            io.BytesIO(build_tar_bytes({"a.txt": b"12", "b.txt": b"34"}))
        )

    monkeypatch.setattr(distribution_service, "MAX_EXPANDED_BYTES", 100)
    monkeypatch.setattr(distribution_service, "MAX_ARCHIVE_ENTRIES", 1)
    with pytest.raises(
        distribution_service.DeliveryArtifactError,
        match="too many entries",
    ):
        distribution_service.DistributionService._validate_archive(
            io.BytesIO(build_tar_bytes({"a.txt": b"a", "b.txt": b"b"}))
        )


class TrackingStream(io.BytesIO):
    was_closed = False

    def close(self) -> None:
        self.was_closed = True
        super().close()


class PreparedService:
    def __init__(self, prepared: PreparedDelivery) -> None:
        self.prepared = prepared

    def prepare(self, organization_id: str, version_id: str) -> PreparedDelivery:
        assert organization_id == "org-acme"
        assert version_id == "version-1"
        return self.prepared


def build_prepared_response() -> tuple[object, TrackingStream]:
    stream = TrackingStream(b"artifact")
    prepared = PreparedDelivery(
        metadata=DeliveryMetadata(
            schema_version=1,
            organization_id="org-acme",
            asset_id="asset-1",
            version_id="version-1",
            slug="workflow",
            version="1.0.0",
            manifest={},
            manifest_sha256="0" * 64,
            artifact_sha256="1" * 64,
            artifact_size=8,
        ),
        stream=stream,
    )
    response = download_artifact(
        "version-1",
        Actor(
            organization_id="org-acme",
            subject_id="developer-1",
            roles=frozenset({"developer"}),
        ),
        PreparedService(prepared),
    )
    return response, stream


def invoke_asgi_response(response, send) -> None:
    async def receive():
        return {"type": "http.disconnect"}

    asyncio.run(
        response(
            {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "method": "GET",
                "path": "/",
                "headers": [],
            },
            receive,
            send,
        )
    )


def test_artifact_response_closes_spool_when_send_fails_before_first_chunk() -> None:
    response, stream = build_prepared_response()

    async def failing_send(message):
        del message
        raise OSError("client disconnected")

    with pytest.raises(ClientDisconnect):
        invoke_asgi_response(response, failing_send)

    assert stream.closed is True


def test_artifact_response_closes_spool_when_send_is_cancelled() -> None:
    response, stream = build_prepared_response()

    async def cancelled_send(message):
        del message
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        invoke_asgi_response(response, cancelled_send)

    assert stream.closed is True


def test_artifact_response_closes_spool_when_response_construction_fails(
    monkeypatch,
) -> None:
    from web.api.distribution import routes

    stream = TrackingStream(b"artifact")
    prepared = PreparedDelivery(
        metadata=DeliveryMetadata(
            schema_version=1,
            organization_id="org-acme",
            asset_id="asset-1",
            version_id="version-1",
            slug="workflow",
            version="1.0.0",
            manifest={},
            manifest_sha256="0" * 64,
            artifact_sha256="1" * 64,
            artifact_size=8,
        ),
        stream=stream,
    )

    def fail_response_construction(*args, **kwargs):
        del args, kwargs
        raise RuntimeError("response construction failed")

    monkeypatch.setattr(
        routes,
        "PreparedStreamingResponse",
        fail_response_construction,
    )

    with pytest.raises(RuntimeError, match="response construction failed"):
        download_artifact(
            "version-1",
            Actor(
                organization_id="org-acme",
                subject_id="developer-1",
                roles=frozenset({"developer"}),
            ),
            PreparedService(prepared),
        )

    assert stream.closed is True


def test_delivery_closes_artifact_source_and_response_stream(
    registry_client,
    monkeypatch,
) -> None:
    _, version, artifact_bytes = create_published_distribution(registry_client)
    source = TrackingStream(artifact_bytes)
    prepared_streams: list[object] = []

    monkeypatch.setattr(
        registry_client.app.state.artifact_storage,
        "open",
        lambda key: source,
    )

    from web.api.distribution.service import DistributionService

    original_prepare = DistributionService.prepare

    def track_prepare(self, organization_id, version_id):
        prepared = original_prepare(self, organization_id, version_id)
        if prepared is not None:
            prepared_streams.append(prepared.stream)
        return prepared

    monkeypatch.setattr(DistributionService, "prepare", track_prepare)

    response = registry_client.get(
        f"/api/registry/versions/{version['id']}/artifact",
        headers=build_headers(subject_id="developer-1", roles="developer"),
    )

    assert response.status_code == 200
    assert source.was_closed is True
    assert len(prepared_streams) == 1
    assert prepared_streams[0].closed is True
