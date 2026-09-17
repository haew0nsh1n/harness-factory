from __future__ import annotations

import hashlib
import io
import stat
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from harness_factory import generate_package, load_json, validate, validate_scenarios
from harness_factory.contracts import no_symlinks, require
from web.api.designs.digest import canonical_json_bytes, design_digest
from web.api.designs.models import CONTENT_LANGUAGE_DEFAULT, CONTENT_LANGUAGES
from web.api.designs.repository import ensure_sqlite_write_transaction
from web.api.organizations.models import Organization
from web.api.registry.models import Asset, AssetVersion

SAMPLE_REGISTRY_NAMESPACE = UUID("7b8f881b-791e-48ad-bf23-19b78ff8c95f")
SAMPLE_TEMPLATE_KEYS = (
    "issue-planning",
    "test-first-implementation",
    "code-review",
    "manual-handoff",
    "full-sdlc-delivery",
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


def sample_asset_id(
    organization_id: str, template_key: str, language: str = CONTENT_LANGUAGE_DEFAULT
) -> str:
    suffix = "" if language == CONTENT_LANGUAGE_DEFAULT else f":{language}"
    return str(
        uuid5(
            SAMPLE_REGISTRY_NAMESPACE,
            f"{organization_id}:{template_key}{suffix}:asset",
        )
    )


def sample_version_id(
    organization_id: str, template_key: str, language: str = CONTENT_LANGUAGE_DEFAULT
) -> str:
    suffix = "" if language == CONTENT_LANGUAGE_DEFAULT else f":{language}"
    return str(
        uuid5(
            SAMPLE_REGISTRY_NAMESPACE,
            f"{organization_id}:{template_key}{suffix}:{SAMPLE_VERSION}",
        )
    )


def sample_slug(
    template_key: str, language: str = CONTENT_LANGUAGE_DEFAULT
) -> str:
    if language == CONTENT_LANGUAGE_DEFAULT:
        return template_key
    return f"{template_key}-{language}"


def seed_sample_registry(
    session: Session,
    *,
    organization_id: str,
    actor_id: str,
    artifact_root: Path,
    language: str = CONTENT_LANGUAGE_DEFAULT,
) -> list[SampleRegistrySeedResult]:
    if language not in CONTENT_LANGUAGES:
        raise SampleRegistrySeedInvalid(f"unsupported sample language: {language}")
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
        sample = _load_sample(template_key, language)
        slug = sample_slug(template_key, language)
        asset_id = sample_asset_id(organization_id, template_key, language)
        version_id = sample_version_id(organization_id, template_key, language)
        artifact_key = (
            f"organizations/{organization_id}/samples/{slug}/"
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
                "slug": slug,
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
            slug=slug,
            language=language,
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


def _load_sample(
    template_key: str, language: str = CONTENT_LANGUAGE_DEFAULT
) -> _Sample:
    root = _repository_root()
    fixture_root = root / "examples" / "sample-workflows" / template_key
    if language != CONTENT_LANGUAGE_DEFAULT:
        fixture_root = fixture_root / language
    catalog_path = root / "catalog" / "catalog.json"
    profile = load_json(fixture_root / "profile.json")
    workflow = load_json(fixture_root / "workflow.json")
    scenarios = load_json(fixture_root / "scenarios.json")
    catalog = load_json(catalog_path)
    validate(profile, workflow, catalog, catalog_path.parent)
    validate_scenarios(scenarios, workflow)
    return _Sample(
        profile=profile,
        workflow=workflow,
        scenarios=scenarios,
        catalog=catalog,
        artifact=_build_full_package(
            profile, workflow, scenarios, catalog, catalog_path.parent
        ),
    )


def _build_full_package(
    profile: dict[str, object],
    workflow: dict[str, object],
    scenarios: dict[str, object],
    catalog: dict[str, object],
    catalog_root: Path,
) -> bytes:
    # Emit the same complete package a real build produces so registry samples
    # download the full harness bundle, not a JSON-only placeholder.
    with tempfile.TemporaryDirectory() as workspace:
        root = Path(workspace).resolve()
        package_root = root / "package"
        generate_package(
            profile, workflow, scenarios, catalog, catalog_root, package_root
        )
        archive_path = root / "package.tar"
        _write_deterministic_tar(package_root, archive_path)
        return archive_path.read_bytes()


def _write_deterministic_tar(package_root: Path, archive_path: Path) -> None:
    root = no_symlinks(package_root)
    entries = sorted(no_symlinks(path) for path in root.rglob("*"))
    with tarfile.open(archive_path, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path in entries:
            relative = path.relative_to(root).as_posix()
            require(relative, "archive: empty relative path")
            info = tarfile.TarInfo(relative)
            info.mode = stat.S_IMODE(path.stat().st_mode)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
                continue
            require(path.is_file(), f"archive: unsupported entry {relative}")
            data = path.read_bytes()
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


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
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == expected_digest:
        return
    # Overwrite when the package bytes change (updated code or fixtures).
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
    slug: str,
    language: str,
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
        _resync_existing(
            asset,
            version,
            organization_id=organization_id,
            slug=slug,
            asset_id=asset_id,
            version_id=version_id,
            name=name,
            description=description,
            manifest=manifest,
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
                    slug=slug,
                    name=name,
                    language=language,
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
        _resync_existing(
            asset,
            version,
            organization_id=organization_id,
            slug=slug,
            asset_id=asset_id,
            version_id=version_id,
            name=name,
            description=description,
            manifest=manifest,
            manifest_digest=manifest_digest,
            artifact_key=artifact_key,
            artifact_digest=artifact_digest,
        )
        return False


def _resync_existing(
    asset: Asset | None,
    version: AssetVersion | None,
    *,
    organization_id: str,
    slug: str,
    asset_id: str,
    version_id: str,
    name: str,
    description: str,
    manifest: dict[str, object],
    manifest_digest: str,
    artifact_key: str,
    artifact_digest: str,
) -> None:
    identity_ok = (
        asset is not None
        and version is not None
        and asset.id == asset_id
        and asset.organization_id == organization_id
        and asset.kind == "workflow"
        and asset.slug == slug
        and version.id == version_id
        and version.organization_id == organization_id
        and version.asset_id == asset_id
        and version.version == SAMPLE_VERSION
    )
    if not identity_ok:
        raise SampleRegistrySeedInvalid(
            f"sample registry identity collision: {slug}"
        )
    # Re-sync sample content so redeploys with updated code or fixtures stay consistent.
    asset.name = name
    asset.description = description
    version.manifest_json = manifest
    version.digest = manifest_digest
    version.artifact_key = artifact_key
    version.artifact_digest = artifact_digest
    version.status = "published"
    version.channel = "stable"
