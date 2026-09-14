from __future__ import annotations

import hashlib
import shutil
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from harness_factory import load_json
from harness_factory.errors import PackageError
from web.api.builds.models import (
    BUILD_STATUS_FAILED,
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
    BUILD_STATUS_SUCCEEDED,
    BuildJob,
)
from web.api.config import Settings, get_settings
from web.api.db import Base
from web.api.designs.digest import design_digest
from web.api.designs.models import (
    APPROVAL_DECISION_APPROVED,
    APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
    Approval,
    DESIGN_STATUS_APPROVED,
    DESIGN_STATUS_BUILD_QUEUED,
    DESIGN_STATUS_BUILT,
    DESIGN_STATUS_FAILED,
    HarnessDesign,
)
from web.api.identity.models import Actor
from web.api.main import create_app
from web.api.organizations.models import Organization


FIXTURE_ROOT = Path(__file__).resolve().parents[2]


def load_design_fixture(name: str) -> dict[str, object]:
    if name == "catalog":
        return load_json(FIXTURE_ROOT / "catalog" / "catalog.json")
    return load_json(FIXTURE_ROOT / "examples" / "github-issue" / f"{name}.json")


def build_design_payload() -> dict[str, object]:
    profile = load_design_fixture("profile")
    return {
        "customer_id": profile["customer_id"],
        "name": profile["name"],
        "profile": profile,
        "workflow": load_design_fixture("workflow"),
        "scenarios": load_design_fixture("scenarios"),
        "catalog": load_design_fixture("catalog"),
    }


def build_headers(
    *,
    organization_id: str = "org-acme",
    subject_id: str = "author-1",
    roles: str = "author",
) -> dict[str, str]:
    return {
        "X-HF-Organization": organization_id,
        "X-HF-Subject": subject_id,
        "X-HF-Roles": roles,
    }


def build_actor(
    *,
    organization_id: str = "org-acme",
    subject_id: str = "author-1",
    roles: frozenset[str] = frozenset({"author"}),
) -> Actor:
    return Actor(
        organization_id=organization_id,
        subject_id=subject_id,
        roles=roles,
    )


def create_sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@dataclass
class RecordingWorkspaceFactory:
    root: Path
    created_paths: list[Path]

    def __call__(self):
        index = len(self.created_paths)
        path = self.root / f"workspace-{index}"

        @contextmanager
        def manager() -> Iterator[Path]:
            path.mkdir(parents=True)
            self.created_paths.append(path)
            try:
                yield path
            finally:
                shutil.rmtree(path)

        return manager()


@pytest.fixture
def build_client(tmp_path) -> Iterator[TestClient]:
    app = create_app(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url="sqlite+pysqlite:///:memory:",
            catalog_root=FIXTURE_ROOT / "catalog",
            artifact_root=tmp_path / "artifacts",
        )
    )
    Base.metadata.create_all(app.state.engine)
    with Session(app.state.engine) as session:
        session.add_all(
            [
                Organization(
                    id="org-acme",
                    entra_tenant_id="tenant-acme",
                    name="Acme",
                ),
                Organization(
                    id="org-umbrella",
                    entra_tenant_id="tenant-umbrella",
                    name="Umbrella",
                ),
            ]
        )
        session.commit()

    with TestClient(app) as client:
        yield client


def create_design(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/designs",
        headers=build_headers(),
        json=build_design_payload(),
    )
    assert response.status_code == 201
    return response.json()["design"]


def approve_design(client: TestClient) -> dict[str, object]:
    created = create_design(client)
    validated = client.post(
        f"/api/designs/{created['id']}/validate",
        headers=build_headers(),
    )
    assert validated.status_code == 200
    reviewed = client.post(
        f"/api/designs/{created['id']}/reviews",
        headers=build_headers(subject_id="reviewer-1", roles="reviewer"),
        json={
            "expected_digest": validated.json()["design"]["digest"],
            "decision": "approved",
        },
    )
    assert reviewed.status_code == 200
    return reviewed.json()["design"]


def seed_organization(session: Session, organization_id: str = "org-acme") -> None:
    if session.get(Organization, organization_id) is None:
        session.add(
            Organization(
                id=organization_id,
                entra_tenant_id=f"tenant-{organization_id}",
                name=organization_id,
            )
        )
        session.flush()


def seed_design(
    session: Session,
    *,
    design_id: str = "design-1",
    organization_id: str = "org-acme",
    status: str = DESIGN_STATUS_APPROVED,
    create_approval: bool = True,
) -> HarnessDesign:
    payload = build_design_payload()
    workflow = deepcopy(payload["workflow"])
    workflow["steps"][0]["completion"] = f"{workflow['steps'][0]['completion']} ({design_id})"
    digest = design_digest(
        payload["profile"],
        workflow,
        payload["scenarios"],
        payload["catalog"],
    )
    design = HarnessDesign(
        id=design_id,
        organization_id=organization_id,
        customer_id=payload["customer_id"],
        name=f"{payload['name']} {design_id}",
        profile_json=payload["profile"],
        workflow_json=workflow,
        scenarios_json=payload["scenarios"],
        catalog_json=payload["catalog"],
        validation_findings_json=None,
        revision=1,
        digest=digest,
        status=status,
        created_by="author-1",
    )
    session.add(design)
    session.flush()
    if create_approval:
        session.add(
            Approval(
                id=f"approval-{design_id}",
                organization_id=organization_id,
                subject_type=APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                subject_id=design_id,
                subject_digest=digest,
                decision=APPROVAL_DECISION_APPROVED,
                actor_subject_id="reviewer-1",
            )
        )
        session.flush()
    return design


def create_build_service(
    session: Session,
    tmp_path: Path,
    *,
    workspace_factory: RecordingWorkspaceFactory | None = None,
    package_generator=None,
    package_checker=None,
):
    from web.api.builds.repository import BuildJobRepository
    from web.api.builds.service import BuildService
    from web.api.builds.storage import FileArtifactStorage

    return BuildService(
        repository=BuildJobRepository(session),
        settings=Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url="sqlite+pysqlite:///:memory:",
            catalog_root=FIXTURE_ROOT / "catalog",
            artifact_root=tmp_path / "artifacts",
        ),
        storage=FileArtifactStorage(tmp_path / "artifacts"),
        workspace_factory=workspace_factory or RecordingWorkspaceFactory(
            root=tmp_path,
            created_paths=[],
        ),
        package_generator=package_generator,
        package_checker=package_checker,
    )


def test_file_artifact_storage_put_once_stores_exact_bytes_and_reuses_matching_bytes(
    tmp_path,
):
    from web.api.builds.storage import FileArtifactStorage

    source = tmp_path / "package.tar"
    source.write_bytes(b"artifact-bytes\n")
    storage = FileArtifactStorage(tmp_path / "artifacts")
    key = (
        "organizations/org-acme/designs/design-1/"
        + ("d" * 64)
        + "/package.tar"
    )

    stored = storage.put_once(key, source)
    duplicate = storage.put_once(key, source)

    assert stored.key == key
    assert stored.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert stored.size == len(source.read_bytes())
    assert duplicate == stored
    assert (tmp_path / "artifacts" / key).read_bytes() == source.read_bytes()
    with storage.open(key) as stream:
        assert stream.read() == source.read_bytes()


def test_file_artifact_storage_rejects_conflicting_bytes_unsafe_keys_and_non_files(
    tmp_path,
):
    from web.api.builds.storage import (
        ArtifactConflict,
        ArtifactStorageError,
        FileArtifactStorage,
    )

    storage = FileArtifactStorage(tmp_path / "artifacts")
    key = (
        "organizations/org-acme/designs/design-1/"
        + ("d" * 64)
        + "/package.tar"
    )
    first = tmp_path / "first.tar"
    first.write_bytes(b"first")
    storage.put_once(key, first)

    second = tmp_path / "second.tar"
    second.write_bytes(b"second")
    with pytest.raises(ArtifactConflict):
        storage.put_once(key, second)

    directory_source = tmp_path / "directory"
    directory_source.mkdir()
    with pytest.raises(ArtifactStorageError):
        storage.put_once(key, directory_source)

    with pytest.raises(ArtifactStorageError):
        storage.put_once("../escape.tar", first)


def test_submit_requires_approved_exact_digest_and_exact_approval(tmp_path):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(
            session,
            status=DESIGN_STATUS_APPROVED,
            create_approval=False,
        )
        session.commit()

        from web.api.builds.service import (
            BuildDigestMismatch,
            InvalidBuildLifecycle,
        )

        service = create_build_service(session, tmp_path)

        with pytest.raises(InvalidBuildLifecycle):
            service.submit(build_actor(), design.id, design.digest)

        with pytest.raises(BuildDigestMismatch):
            service.submit(build_actor(), design.id, "f" * 64)

        session.add(
            Approval(
                id="approval-design-1-exact",
                organization_id="org-acme",
                subject_type=APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                subject_id=design.id,
                subject_digest=design.digest,
                decision=APPROVAL_DECISION_APPROVED,
                actor_subject_id="reviewer-1",
            )
        )
        session.commit()

        job = service.submit(build_actor(), design.id, design.digest)
        session.refresh(design)

    assert job.status == BUILD_STATUS_QUEUED
    assert design.status == DESIGN_STATUS_BUILD_QUEUED


def test_duplicate_submission_returns_existing_queued_and_successful_job(tmp_path):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(session)
        session.commit()
        service = create_build_service(session, tmp_path)

        queued = service.submit(build_actor(), design.id, design.digest)
        duplicate = service.submit(build_actor(), design.id, design.digest)

        assert duplicate.id == queued.id
        assert session.scalars(select(BuildJob)).all() == [queued]

        processed = service.run_next()
        successful = service.submit(build_actor(), design.id, design.digest)

    assert processed is not None
    assert processed.id == queued.id
    assert processed.status == BUILD_STATUS_SUCCEEDED
    assert successful.id == queued.id


def test_submit_handles_uniqueness_race_and_returns_existing_job(tmp_path):
    database_path = tmp_path / "build-race.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    Base.metadata.create_all(engine)

    with Session(engine) as seed_session:
        seed_organization(seed_session)
        design = seed_design(seed_session)
        seed_session.commit()
        expected_digest = design.digest

    with Session(engine) as session_one, Session(engine) as session_two:
        from web.api.builds.repository import BuildJobRepository
        from web.api.builds.service import BuildService
        from web.api.builds.storage import FileArtifactStorage

        concurrent_service = create_build_service(session_two, tmp_path)

        class RacingBuildJobRepository(BuildJobRepository):
            def __init__(self, session: Session) -> None:
                super().__init__(session)
                self._injected_race = False

            def find_by_identity(
                self,
                organization_id: str,
                design_id: str,
                design_digest: str,
            ) -> BuildJob | None:
                if not self._injected_race:
                    self._injected_race = True
                    concurrent_service.submit(
                        build_actor(),
                        design_id,
                        design_digest,
                    )
                    session_two.commit()
                    return None
                return super().find_by_identity(
                    organization_id,
                    design_id,
                    design_digest,
                )

        service = BuildService(
            repository=RacingBuildJobRepository(session_one),
            settings=Settings(
                auth_mode="development",
            allow_insecure_development_auth=True,
                database_url=f"sqlite+pysqlite:///{database_path}",
                catalog_root=FIXTURE_ROOT / "catalog",
                artifact_root=tmp_path / "artifacts",
            ),
            storage=FileArtifactStorage(tmp_path / "artifacts"),
        )

        build = service.submit(build_actor(), "design-1", expected_digest)
        build_id = build.id if build is not None else None
        session_one.commit()

    with Session(engine) as check_session:
        jobs = check_session.scalars(select(BuildJob)).all()
        design = check_session.get(HarnessDesign, "design-1")

    assert build is not None
    assert len(jobs) == 1
    assert build_id == jobs[0].id
    assert jobs[0].status == BUILD_STATUS_QUEUED
    assert design is not None
    assert design.status == DESIGN_STATUS_BUILD_QUEUED


def test_submit_rechecks_current_design_digest_before_returning_existing_job(tmp_path):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(session)
        session.commit()
        service = create_build_service(session, tmp_path)

        original_digest = design.digest
        service.submit(build_actor(), design.id, original_digest)
        service.run_next()
        design.digest = "f" * 64
        session.flush()

        from web.api.builds.service import BuildDigestMismatch

        with pytest.raises(BuildDigestMismatch):
            service.submit(build_actor(), design.id, original_digest)


@pytest.mark.parametrize(
    ("approval_decision", "approval_digest"),
    [
        ("rejected", None),
        ("approved", "f" * 64),
    ],
)
def test_submit_rejects_reuse_when_effective_approval_is_stale_or_rejected(
    tmp_path,
    approval_decision,
    approval_digest,
):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(session)
        session.commit()
        service = create_build_service(session, tmp_path)

        queued = service.submit(build_actor(), design.id, design.digest)
        if queued is not None:
            queued.status = BUILD_STATUS_RUNNING
            session.flush()
            queued.status = BUILD_STATUS_SUCCEEDED
            design.status = DESIGN_STATUS_BUILT
            session.flush()

        session.add(
            Approval(
                id=f"approval-{approval_decision}",
                organization_id="org-acme",
                subject_type=APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                subject_id=design.id,
                subject_digest=design.digest if approval_digest is None else approval_digest,
                decision=approval_decision,
                actor_subject_id="reviewer-2",
            )
        )
        session.commit()

        from web.api.builds.service import InvalidBuildLifecycle

        with pytest.raises(InvalidBuildLifecycle):
            service.submit(build_actor(), design.id, design.digest)


def test_run_next_builds_checks_archives_and_stores_a_deterministic_artifact(tmp_path):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)
    workspace_factory = RecordingWorkspaceFactory(
        root=tmp_path,
        created_paths=[],
    )

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(session)
        session.commit()
        service = create_build_service(
            session,
            tmp_path,
            workspace_factory=workspace_factory,
        )
        queued = service.submit(build_actor(), design.id, design.digest)

        processed = service.run_next()
        session.refresh(design)

    assert processed is not None
    assert processed.id == queued.id
    assert processed.status == BUILD_STATUS_SUCCEEDED
    assert processed.error_code is None
    assert processed.artifact_key == (
        f"organizations/org-acme/designs/{design.id}/{design.digest}/package.tar"
    )
    assert processed.artifact_digest is not None
    assert design.status == DESIGN_STATUS_BUILT
    assert workspace_factory.created_paths
    assert all(not path.exists() for path in workspace_factory.created_paths)

    artifact_path = tmp_path / "artifacts" / processed.artifact_key
    artifact_bytes = artifact_path.read_bytes()
    assert hashlib.sha256(artifact_bytes).hexdigest() == processed.artifact_digest

    with tarfile.open(artifact_path) as archive:
        members = archive.getmembers()

    assert [member.name for member in members] == sorted(
        member.name for member in members
    )
    for member in members:
        assert member.uid == 0
        assert member.gid == 0
        assert member.uname == ""
        assert member.gname == ""
        assert member.mtime == 0


def test_failed_build_records_only_a_structured_error_code_and_leaves_no_artifact(
    tmp_path,
):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)
    workspace_factory = RecordingWorkspaceFactory(
        root=tmp_path,
        created_paths=[],
    )

    def fail_generation(*args, **kwargs):
        del args, kwargs
        raise PackageError("generation: boom")

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(session)
        session.commit()
        service = create_build_service(
            session,
            tmp_path,
            workspace_factory=workspace_factory,
            package_generator=fail_generation,
        )
        service.submit(build_actor(), design.id, design.digest)

        processed = service.run_next()
        session.refresh(design)

    assert processed is not None
    assert processed.status == BUILD_STATUS_FAILED
    assert processed.error_code == "generation-failed"
    assert processed.artifact_key is None
    assert processed.artifact_digest is None
    assert design.status == DESIGN_STATUS_FAILED
    assert workspace_factory.created_paths
    assert all(not path.exists() for path in workspace_factory.created_paths)
    assert list((tmp_path / "artifacts").rglob("*.tar")) == []


def test_failed_build_resubmission_reuses_and_resets_same_job(tmp_path):
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    def fail_generation(*args, **kwargs):
        del args, kwargs
        raise PackageError("generation: boom")

    with Session(engine) as session:
        seed_organization(session)
        design = seed_design(session)
        session.commit()

        failing_service = create_build_service(
            session,
            tmp_path,
            package_generator=fail_generation,
        )
        original = failing_service.submit(build_actor(), design.id, design.digest)
        failed = failing_service.run_next()
        failed_id = failed.id if failed is not None else None
        assert failed is not None
        assert failed.status == BUILD_STATUS_FAILED

        retry_service = create_build_service(session, tmp_path)
        retried = retry_service.submit(build_actor(), design.id, design.digest)
        session.refresh(design)
        jobs = session.scalars(select(BuildJob)).all()

    assert original is not None
    assert failed_id == original.id
    assert retried is not None
    assert retried.id == original.id
    assert retried.status == BUILD_STATUS_QUEUED
    assert retried.error_code is None
    assert retried.artifact_key is None
    assert retried.artifact_digest is None
    assert retried.started_at is None
    assert retried.finished_at is None
    assert design.status == DESIGN_STATUS_BUILD_QUEUED
    assert len(jobs) == 1
    assert jobs[0].id == original.id
    assert jobs[0].status == BUILD_STATUS_QUEUED


def test_build_routes_queue_and_fetch_status_idempotently(build_client):
    approved = approve_design(build_client)

    queued = build_client.post(
        f"/api/designs/{approved['id']}/builds",
        headers=build_headers(),
        json={"expected_digest": approved["digest"]},
    )

    assert queued.status_code == 202
    build = queued.json()["build"]
    assert build["status"] == "queued"
    assert build["design_id"] == approved["id"]
    assert build["design_digest"] == approved["digest"]

    duplicate = build_client.post(
        f"/api/designs/{approved['id']}/builds",
        headers=build_headers(),
        json={"expected_digest": approved["digest"]},
    )

    assert duplicate.status_code == 202
    assert duplicate.json()["build"]["id"] == build["id"]

    fetched = build_client.get(
        f"/api/builds/{build['id']}",
        headers=build_headers(),
    )

    assert fetched.status_code == 200
    assert fetched.json()["build"] == duplicate.json()["build"]


def test_worker_cli_once_processes_at_most_one_job(tmp_path, monkeypatch):
    from web.api.builds.worker import main

    database_path = tmp_path / "worker.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        seed_organization(session)
        design_one = seed_design(session, design_id="design-1")
        design_two = seed_design(session, design_id="design-2")
        session.add_all(
            [
                BuildJob(
                    id="build-1",
                    organization_id="org-acme",
                    design_id=design_one.id,
                    design_digest=design_one.digest,
                    status=BUILD_STATUS_QUEUED,
                    attempts=0,
                ),
                BuildJob(
                    id="build-2",
                    organization_id="org-acme",
                    design_id=design_two.id,
                    design_digest=design_two.digest,
                    status=BUILD_STATUS_QUEUED,
                    attempts=0,
                ),
            ]
        )
        design_one.status = DESIGN_STATUS_BUILD_QUEUED
        design_two.status = DESIGN_STATUS_BUILD_QUEUED
        session.commit()

    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    monkeypatch.setenv("HF_AUTH_MODE", "development")
    monkeypatch.setenv("HF_CATALOG_ROOT", str(FIXTURE_ROOT / "catalog"))
    monkeypatch.setenv("HF_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    get_settings.cache_clear()

    try:
        assert main(["--once"]) == 0
    finally:
        get_settings.cache_clear()
        engine.dispose()

    check_engine = create_engine(database_url)
    with Session(check_engine) as session:
        builds = {
            build.id: build.status
            for build in session.scalars(select(BuildJob).order_by(BuildJob.id.asc())).all()
        }

    assert list(builds.values()).count(BUILD_STATUS_SUCCEEDED) == 1
    assert list(builds.values()).count(BUILD_STATUS_QUEUED) == 1
    check_engine.dispose()
