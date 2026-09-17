from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Select, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from web.api.builds.models import (
    BUILD_STATUS_FAILED,
    BUILD_STATUS_QUEUED,
    BUILD_STATUS_RUNNING,
    BUILD_STATUS_SUCCEEDED,
    BuildJob,
)
from web.api.builds.storage import StoredArtifact
from web.api.designs.models import (
    APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
    Approval,
    DESIGN_STATUS_BUILD_QUEUED,
    DESIGN_STATUS_BUILT,
    DESIGN_STATUS_FAILED,
    HarnessDesign,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class BuildJobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, organization_id: str, build_id: str) -> BuildJob | None:
        return self._session.scalar(
            select(BuildJob).where(
                BuildJob.organization_id == organization_id,
                BuildJob.id == build_id,
            )
        )

    def get_design(self, organization_id: str, design_id: str) -> HarnessDesign | None:
        return self._session.scalar(
            select(HarnessDesign).where(
                HarnessDesign.organization_id == organization_id,
                HarnessDesign.id == design_id,
            )
        )

    def latest_design_approval(
        self, organization_id: str, design_id: str
    ) -> Approval | None:
        return self._session.scalar(
            select(Approval)
            .where(
                Approval.organization_id == organization_id,
                Approval.subject_type == APPROVAL_SUBJECT_TYPE_HARNESS_DESIGN,
                Approval.subject_id == design_id,
            )
            .order_by(Approval.created_at.desc(), Approval.id.desc())
            .limit(1)
        )

    def find_by_identity(
        self,
        organization_id: str,
        design_id: str,
        design_digest: str,
    ) -> BuildJob | None:
        return self._session.scalar(
            select(BuildJob)
            .where(
                BuildJob.organization_id == organization_id,
                BuildJob.design_id == design_id,
                BuildJob.design_digest == design_digest,
            )
            .order_by(BuildJob.created_at.desc(), BuildJob.id.desc())
            .limit(1)
        )

    def list_recent_for_design(
        self,
        organization_id: str,
        design_id: str,
        limit: int = 3,
    ) -> list[BuildJob]:
        return list(
            self._session.scalars(
                select(BuildJob)
                .where(
                    BuildJob.organization_id == organization_id,
                    BuildJob.design_id == design_id,
                )
                .order_by(BuildJob.created_at.desc(), BuildJob.id.desc())
                .limit(limit)
            )
        )

    def create(
        self,
        organization_id: str,
        design_id: str,
        design_digest: str,
    ) -> BuildJob:
        try:
            with self._session.begin_nested():
                job = BuildJob(
                    id=str(uuid4()),
                    organization_id=organization_id,
                    design_id=design_id,
                    design_digest=design_digest,
                    status=BUILD_STATUS_QUEUED,
                    attempts=0,
                )
                self._session.add(job)
                self._session.flush()
        except IntegrityError:
            raise
        return job

    def refresh_design(self, design: HarnessDesign) -> HarnessDesign:
        self._session.refresh(design)
        return design

    def mark_design_build_queued(self, design: HarnessDesign) -> None:
        design.status = DESIGN_STATUS_BUILD_QUEUED
        self._session.flush()

    def mark_design_built(self, design: HarnessDesign) -> None:
        design.status = DESIGN_STATUS_BUILT
        self._session.flush()

    def reset_for_retry(self, job: BuildJob) -> BuildJob:
        job.status = BUILD_STATUS_QUEUED
        job.artifact_key = None
        job.artifact_digest = None
        job.error_code = None
        job.started_at = None
        job.finished_at = None
        self._session.flush()
        return job

    def claim_next(self) -> BuildJob | None:
        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            candidate = self._session.scalar(self._queued_query().with_for_update(skip_locked=True))
            if candidate is None:
                return None
            candidate.status = BUILD_STATUS_RUNNING
            candidate.attempts += 1
            candidate.started_at = utcnow()
            candidate.finished_at = None
            candidate.error_code = None
            self._session.flush()
            return candidate

        candidate_id = self._session.scalar(
            select(BuildJob.id)
            .where(BuildJob.status == BUILD_STATUS_QUEUED)
            .order_by(BuildJob.created_at.asc(), BuildJob.id.asc())
            .limit(1)
        )
        if candidate_id is None:
            return None

        started_at = utcnow()
        updated = self._session.execute(
            update(BuildJob)
            .where(
                BuildJob.id == candidate_id,
                BuildJob.status == BUILD_STATUS_QUEUED,
            )
            .values(
                status=BUILD_STATUS_RUNNING,
                attempts=BuildJob.attempts + 1,
                started_at=started_at,
                finished_at=None,
                error_code=None,
            )
        )
        if updated.rowcount != 1:
            return None
        self._session.flush()
        return self._session.get(BuildJob, candidate_id)

    def mark_succeeded(self, job: BuildJob, artifact: StoredArtifact) -> None:
        design = self.get_design(job.organization_id, job.design_id)
        job.status = BUILD_STATUS_SUCCEEDED
        job.artifact_key = artifact.key
        job.artifact_digest = artifact.sha256
        job.error_code = None
        job.finished_at = utcnow()
        if design is not None:
            design.status = DESIGN_STATUS_BUILT
        self._session.flush()

    def mark_failed(self, job: BuildJob, error_code: str) -> None:
        design = self.get_design(job.organization_id, job.design_id)
        job.status = BUILD_STATUS_FAILED
        job.artifact_key = None
        job.artifact_digest = None
        job.error_code = error_code
        job.finished_at = utcnow()
        if design is not None:
            design.status = DESIGN_STATUS_FAILED
        self._session.flush()

    @staticmethod
    def _queued_query() -> Select[tuple[BuildJob]]:
        return (
            select(BuildJob)
            .where(BuildJob.status == BUILD_STATUS_QUEUED)
            .order_by(BuildJob.created_at.asc(), BuildJob.id.asc())
            .limit(1)
        )
