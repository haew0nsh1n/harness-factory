from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from harness_factory import load_json, validate, validate_scenarios
from web.api.designs.digest import canonical_json_bytes, design_digest
from web.api.designs.repository import ensure_sqlite_write_transaction
from web.api.organizations.models import Organization
from web.api.registry.models import Asset, AssetVersion

SAMPLE_REGISTRY_NAMESPACE = UUID("7b8f881b-791e-48ad-bf23-19b78ff8c95f")
SAMPLE_TEMPLATE_KEYS = (
    "issue-planning",
    "test-first-implementation",
    "code-review",
    "manual-handoff",
)
SAMPLE_VERSION = "1.0.0"


class SampleRegistrySeedInvalid(RuntimeError):
    pass


@dataclass(frozen=True)
class SampleRegistrySeedResult:
    asset_id: str
    version_id: str
    template_key: str
    created: bool


@dataclass(frozen=True)
class _Sample:
    profile: dict[str, object]
    workflow: dict[str, object]
    scenarios: dict[str, object]
    catalog: dict[str, object]
    artifact: bytes


def sample_asset_id(organization_id: str, template_key: str) -> str:
    return str(
        uuid5(
            SAMPLE_REGISTRY_NAMESPACE,
            f"{organization_id}:{template_key}:asset",
        )
    )


def sample_version_id(organization_id: str, template_key: str) -> str:
    return str(
        uuid5(
            SAMPLE_REGISTRY_NAMESPACE,
            f"{organization_id}:{template_key}:{SAMPLE_VERSION}",
        )
    )


def seed_sample_registry(
    session: Session,
    *,
    organization_id: str,
    actor_id: str,
    artifact_root: Path,
) -> list[SampleRegistrySeedResult]:
    ensure_sqlite_write_transaction(session)
    organization = session.scalar(
        select(Organization)
        .where(Organization.id == organization_id)
        .with_for_update()
    )
    if organization is None:
        raise SampleRegistrySeedInvalid(
            f"development organization does not exist: {organization_id}"
        )
    if organization.entra_tenant_id != f"development-{organization_id}":
        raise SampleRegistrySeedInvalid(
            "configured development organization has a conflicting tenant marker"
        )

    results = []
    for template_key in SAMPLE_TEMPLATE_KEYS:
        sample = _load_sample(template_key)
        asset_id = sample_asset_id(organization_id, template_key)
        version_id = sample_version_id(organization_id, template_key)
        artifact_key = (
            f"organizations/{organization_id}/samples/{template_key}/"
            f"{SAMPLE_VERSION}/package.tar"
        )
        artifact_digest = hashlib.sha256(sample.artifact).hexdigest()
        _write_artifact(
            artifact_root,
            artifact_key,
            sample.artifact,
            artifact_digest,
        )
        manifest = {
            "schema_version": 1,
            "asset": {
                "type": "workflow",
                "slug": template_key,
            },
            "version": SAMPLE_VERSION,
            "runtime": "copilot-cli",
            "design_digest": design_digest(
                sample.profile,
                sample.workflow,
                sample.scenarios,
                sample.catalog,
            ),
            "artifact": {
                "sha256": artifact_digest,
                "key": artifact_key,
            },
            "dependencies": [],
        }
        manifest_digest = hashlib.sha256(
            canonical_json_bytes(manifest)
        ).hexdigest()
        created = _insert_or_validate(
            session,
            organization_id=organization_id,
            actor_id=actor_id,
            template_key=template_key,
            asset_id=asset_id,
            version_id=version_id,
            name=str(sample.workflow["name"]),
            description=str(sample.workflow["goal"]),
            manifest=manifest,
            manifest_digest=manifest_digest,
            artifact_key=artifact_key,
            artifact_digest=artifact_digest,
        )
        results.append(
            SampleRegistrySeedResult(
                asset_id=asset_id,
                version_id=version_id,
                template_key=template_key,
                created=created,
            )
        )
    return results


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_sample(template_key: str) -> _Sample:
    root = _repository_root()
    fixture_root = root / "examples" / "sample-workflows" / template_key
    catalog_path = root / "catalog" / "catalog.json"
    profile = load_json(fixture_root / "profile.json")
    workflow = load_json(fixture_root / "workflow.json")
    scenarios = load_json(fixture_root / "scenarios.json")
    catalog = load_json(catalog_path)
    validate(profile, workflow, catalog, catalog_path.parent)
    validate_scenarios(scenarios, workflow)
    documents = (
        ("profile.json", profile),
        ("workflow.json", workflow),
        ("scenarios.json", scenarios),
        ("catalog.json", catalog),
    )
    return _Sample(
        profile=profile,
        workflow=workflow,
        scenarios=scenarios,
        catalog=catalog,
        artifact=_build_archive(documents),
    )


def _build_archive(
    documents: tuple[tuple[str, dict[str, object]], ...],
) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(
        fileobj=buffer,
        mode="w",
        format=tarfile.USTAR_FORMAT,
    ) as archive:
        for name, document in documents:
            content = (
                json.dumps(
                    document,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode()
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def _write_artifact(
    artifact_root: Path,
    artifact_key: str,
    content: bytes,
    expected_digest: str,
) -> None:
    root = artifact_root.resolve()
    target = (root / artifact_key).resolve()
    if root != target and root not in target.parents:
        raise SampleRegistrySeedInvalid("sample artifact path escapes artifact root")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected_digest:
            raise SampleRegistrySeedInvalid(
                f"sample registry artifact collision: {artifact_key}"
            )
        return
    temporary = target.with_name(f".{target.name}.{expected_digest}.tmp")
    temporary.write_bytes(content)
    try:
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _insert_or_validate(
    session: Session,
    *,
    organization_id: str,
    actor_id: str,
    template_key: str,
    asset_id: str,
    version_id: str,
    name: str,
    description: str,
    manifest: dict[str, object],
    manifest_digest: str,
    artifact_key: str,
    artifact_digest: str,
) -> bool:
    asset = session.get(Asset, asset_id)
    version = session.get(AssetVersion, version_id)
    if asset is not None or version is not None:
        _validate_existing(
            asset,
            version,
            organization_id=organization_id,
            template_key=template_key,
            asset_id=asset_id,
            version_id=version_id,
            manifest_digest=manifest_digest,
            artifact_key=artifact_key,
            artifact_digest=artifact_digest,
        )
        return False

    try:
        with session.begin_nested():
            session.add(
                Asset(
                    id=asset_id,
                    organization_id=organization_id,
                    kind="workflow",
                    slug=template_key,
                    name=name,
                    description=description,
                    owner_subject_id=actor_id,
                    visibility="internal",
                    lifecycle="active",
                )
            )
            session.add(
                AssetVersion(
                    id=version_id,
                    organization_id=organization_id,
                    asset_id=asset_id,
                    version=SAMPLE_VERSION,
                    manifest_json=manifest,
                    digest=manifest_digest,
                    artifact_key=artifact_key,
                    artifact_digest=artifact_digest,
                    status="published",
                    channel="stable",
                    created_by=actor_id,
                )
            )
            session.flush()
        return True
    except IntegrityError:
        session.expire_all()
        asset = session.get(Asset, asset_id)
        version = session.get(AssetVersion, version_id)
        _validate_existing(
            asset,
            version,
            organization_id=organization_id,
            template_key=template_key,
            asset_id=asset_id,
            version_id=version_id,
            manifest_digest=manifest_digest,
            artifact_key=artifact_key,
            artifact_digest=artifact_digest,
        )
        return False


def _validate_existing(
    asset: Asset | None,
    version: AssetVersion | None,
    *,
    organization_id: str,
    template_key: str,
    asset_id: str,
    version_id: str,
    manifest_digest: str,
    artifact_key: str,
    artifact_digest: str,
) -> None:
    valid = (
        asset is not None
        and version is not None
        and asset.id == asset_id
        and asset.organization_id == organization_id
        and asset.kind == "workflow"
        and asset.slug == template_key
        and version.id == version_id
        and version.organization_id == organization_id
        and version.asset_id == asset_id
        and version.version == SAMPLE_VERSION
        and version.digest == manifest_digest
        and version.artifact_key == artifact_key
        and version.artifact_digest == artifact_digest
        and version.status == "published"
        and version.channel == "stable"
    )
    if not valid:
        raise SampleRegistrySeedInvalid(
            f"sample registry identity collision: {template_key}"
        )
