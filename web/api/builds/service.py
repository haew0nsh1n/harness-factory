from __future__ import annotations

import io
import stat
import tarfile
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from hmac import compare_digest
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from harness_factory import load_json
from harness_factory.contracts import no_symlinks, require, validate
from harness_factory.errors import HarnessError, PackageError, ValidationError
from harness_factory.package import check_package, generate_package

from web.api.builds.models import (
    BUILD_STATUS_FAILED,
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
    BUILD_STATUS_SUCCEEDED,
    BuildJob,
)
from web.api.builds.repository import BuildJobRepository
from web.api.builds.storage import (
    ArtifactConflict,
    ArtifactStorage,
    ArtifactStorageError,
)
from web.api.config import Settings
from web.api.designs.digest import canonical_json_bytes
from web.api.designs.models import (
    APPROVAL_DECISION_APPROVED,
    DESIGN_STATUS_APPROVED,
    DESIGN_STATUS_BUILT,
    DESIGN_STATUS_BUILD_QUEUED,
    DESIGN_STATUS_FAILED,
    Approval,
    HarnessDesign,
)
from web.api.identity.models import Actor


@dataclass(frozen=True)
class InvalidBuildLifecycle(Exception):
    message: str = "design lifecycle does not allow build"


@dataclass(frozen=True)
class BuildDigestMismatch(Exception):
    message: str = "design digest is stale"


class BuildService:
    def __init__(
        self,
        repository: BuildJobRepository,
        settings: Settings,
        storage: ArtifactStorage,
        *,
        workspace_factory: Callable[[], Iterator[Path]] | None = None,
        package_generator: Callable[..., dict[str, object]] | None = None,
        package_checker: Callable[[Path], dict[str, object]] | None = None,
    ) -> None:
        self._repository = repository
        self._settings = settings
        self._storage = storage
        self._workspace_factory = workspace_factory or self._default_workspace_factory
        self._package_generator = package_generator or generate_package
        self._package_checker = package_checker or check_package

    def get(self, organization_id: str, build_id: str) -> BuildJob | None:
        return self._repository.get(organization_id, build_id)

    def submit(
        self,
        actor: Actor,
        design_id: str,
        expected_digest: str,
    ) -> BuildJob | None:
        design = self._repository.get_design(actor.organization_id, design_id)
        if design is None:
            return None
        if not compare_digest(design.digest, expected_digest):
            raise BuildDigestMismatch()
        approval = self._repository.latest_design_approval(
            actor.organization_id,
            design_id,
        )
        existing = self._repository.find_by_identity(
            actor.organization_id,
            design_id,
            expected_digest,
        )
        if existing is not None:
            return self._reuse_existing_job(design, approval, existing)
        if not self._is_retryable_submission_state(design, approval):
            raise InvalidBuildLifecycle()

        try:
            job = self._repository.create(
                actor.organization_id,
                design.id,
                design.digest,
            )
        except IntegrityError:
            design = self._repository.refresh_design(design)
            approval = self._repository.latest_design_approval(
                actor.organization_id,
                design_id,
            )
            existing = self._repository.find_by_identity(
                actor.organization_id,
                design_id,
                expected_digest,
            )
            if existing is None:
                raise
            return self._reuse_existing_job(design, approval, existing)
        self._repository.mark_design_build_queued(design)
        return job

    def run_next(self) -> BuildJob | None:
        job = self._repository.claim_next()
        if job is None:
            return None

        try:
            with self._workspace_factory() as workspace_root:
                workspace = no_symlinks(Path(workspace_root))
                design = self._repository.get_design(job.organization_id, job.design_id)
                self._require_buildable_design(job, design)
                assert design is not None
                package_root = workspace / "package"
                authoritative_catalog, catalog_root = self._load_authoritative_catalog()
                self._require_matching_catalog_snapshot(
                    design.catalog_json,
                    authoritative_catalog,
                )
                validate(
                    design.profile_json,
                    design.workflow_json,
                    authoritative_catalog,
                    catalog_root,
                )
                self._package_generator(
                    design.profile_json,
                    design.workflow_json,
                    design.scenarios_json,
                    authoritative_catalog,
                    catalog_root,
                    package_root,
                )
                self._package_checker(package_root)

                archive_path = workspace / "package.tar"
                self._write_deterministic_tar(package_root, archive_path)
                artifact = self._storage.put_once(
                    self._artifact_key(job),
                    archive_path,
                )
                self._repository.mark_succeeded(job, artifact)
                return job
        except ValidationError:
            self._repository.mark_failed(job, "validation-failed")
        except PackageError:
            self._repository.mark_failed(job, "generation-failed")
        except ArtifactConflict:
            self._repository.mark_failed(job, "storage-conflict")
        except (ArtifactStorageError, HarnessError, OSError, UnicodeError, tarfile.TarError):
            self._repository.mark_failed(job, "worker-failed")
        return job

    def _has_exact_approval(self, design: HarnessDesign) -> bool:
        approval = self._repository.latest_design_approval(
            design.organization_id,
            design.id,
        )
        return self._is_effectively_approved(design, approval)

    @staticmethod
    def _is_effectively_approved(
        design: HarnessDesign,
        approval: Approval | None,
    ) -> bool:
        return (
            approval is not None
            and approval.decision == APPROVAL_DECISION_APPROVED
            and compare_digest(approval.subject_digest, design.digest)
        )

    def _reuse_existing_job(
        self,
        design: HarnessDesign,
        approval: Approval | None,
        job: BuildJob,
    ) -> BuildJob:
        if not compare_digest(job.design_digest, design.digest):
            raise BuildDigestMismatch()
        if job.status == BUILD_STATUS_FAILED:
            if not self._is_retryable_submission_state(design, approval):
                raise InvalidBuildLifecycle()
            self._repository.reset_for_retry(job)
            self._repository.mark_design_build_queued(design)
            return job
        if not self._is_reusable_submission_state(design, approval, job.status):
            raise InvalidBuildLifecycle()
        return job

    def _is_retryable_submission_state(
        self,
        design: HarnessDesign,
        approval: Approval | None,
    ) -> bool:
        return design.status in {
            DESIGN_STATUS_APPROVED,
            DESIGN_STATUS_FAILED,
        } and self._is_effectively_approved(design, approval)

    def _is_reusable_submission_state(
        self,
        design: HarnessDesign,
        approval: Approval | None,
        build_status: str,
    ) -> bool:
        if not self._is_effectively_approved(design, approval):
            return False
        allowed_design_statuses = {
            BUILD_STATUS_QUEUED: {
                DESIGN_STATUS_APPROVED,
                DESIGN_STATUS_BUILD_QUEUED,
            },
            BUILD_STATUS_RUNNING: {
                DESIGN_STATUS_APPROVED,
                DESIGN_STATUS_BUILD_QUEUED,
            },
            BUILD_STATUS_SUCCEEDED: {
                DESIGN_STATUS_APPROVED,
                DESIGN_STATUS_BUILT,
            },
        }.get(build_status)
        return (
            allowed_design_statuses is not None
            and design.status in allowed_design_statuses
        )

    def _require_buildable_design(
        self,
        job: BuildJob,
        design: HarnessDesign | None,
    ) -> None:
        require(design is not None, "build.design: design not found")
        require(
            design.status == DESIGN_STATUS_BUILD_QUEUED,
            "build.design: design is not queued for build",
        )
        require(
            compare_digest(design.digest, job.design_digest),
            "build.design: design digest changed",
        )
        require(
            self._has_exact_approval(design),
            "build.design: exact approval is required",
        )

    def _load_authoritative_catalog(self) -> tuple[dict[str, object], Path]:
        catalog_root = no_symlinks(self._settings.catalog_root).resolve()
        return load_json(catalog_root / "catalog.json"), catalog_root

    @staticmethod
    def _require_matching_catalog_snapshot(
        design_catalog: dict[str, object],
        authoritative_catalog: dict[str, object],
    ) -> None:
        require(
            canonical_json_bytes(design_catalog)
            == canonical_json_bytes(authoritative_catalog),
            "build.catalog: design snapshot does not match server catalog",
        )

    @staticmethod
    def _artifact_key(job: BuildJob) -> str:
        return (
            f"organizations/{job.organization_id}/designs/"
            f"{job.design_id}/{job.design_digest}/package.tar"
        )

    @contextmanager
    def _default_workspace_factory(self) -> Iterator[Path]:
        workspace_parent = no_symlinks(self._settings.artifact_root).resolve().parent
        workspace_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=workspace_parent,
            prefix="hf-build-",
        ) as root:
            yield Path(root)

    @staticmethod
    def _write_deterministic_tar(package_root: Path, archive_path: Path) -> None:
        root = no_symlinks(package_root)
        entries = sorted(
            no_symlinks(path)
            for path in root.rglob("*")
        )
        with tarfile.open(
            archive_path,
            mode="w",
            format=tarfile.USTAR_FORMAT,
        ) as archive:
            for path in entries:
                relative = path.relative_to(root).as_posix()
                require(relative, "archive: empty relative path")
                if path.is_dir():
                    info = tarfile.TarInfo(relative)
                    info.type = tarfile.DIRTYPE
                    info.mode = stat.S_IMODE(path.stat().st_mode)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = 0
                    archive.addfile(info)
                    continue
                require(path.is_file(), f"archive: unsupported entry {relative}")
                data = path.read_bytes()
                info = tarfile.TarInfo(relative)
                info.size = len(data)
                info.mode = stat.S_IMODE(path.stat().st_mode)
                info.uid = 0
                info.gid = 0
                info.uname = ""
                info.gname = ""
                info.mtime = 0
                archive.addfile(info, io.BytesIO(data))
