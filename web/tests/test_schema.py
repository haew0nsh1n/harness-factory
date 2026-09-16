from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from web.api.config import get_settings
from web.api.db import Base
from web.api.designs.models import HarnessDesign
from web.api.builds.models import BuildJob
from web.api.interviews.models import (
    InterviewOperation,
    InterviewProposal,
    InterviewSession,
    InterviewTurn,
)
from web.api.interviews.service import delete_expired_interviews
from web.api.organizations.models import Organization
from web.api.registry.models import Asset, AssetVersion

REPO_ROOT = Path(__file__).resolve().parents[2]


def create_sqlite_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, connection_record):
        del connection_record
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def create_alembic_config(database_url: str) -> Config:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_schema_registers_required_tables_and_unique_constraints():
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) >= {
        "organizations",
        "memberships",
        "harness_designs",
        "approvals",
        "build_jobs",
        "assets",
        "asset_versions",
        "audit_events",
        "interview_sessions",
        "interview_operations",
        "interview_turns",
        "interview_proposals",
    }

    asset_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("assets")
    }
    build_job_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("build_jobs")
    }
    asset_version_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("asset_versions")
    }

    assert ("organization_id", "slug") in asset_unique_constraints
    assert (
        "organization_id",
        "design_id",
        "design_digest",
    ) in build_job_unique_constraints
    assert ("asset_id", "version") in asset_version_unique_constraints


def test_schema_registers_tenant_columns_and_lookup_indexes():
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    build_job_columns = {
        column["name"]: column for column in inspector.get_columns("build_jobs")
    }
    harness_design_columns = {
        column["name"]: column for column in inspector.get_columns("harness_designs")
    }
    asset_version_columns = {
        column["name"]: column for column in inspector.get_columns("asset_versions")
    }
    build_job_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): tuple(foreign_key["referred_columns"])
        for foreign_key in inspector.get_foreign_keys("build_jobs")
    }
    asset_version_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): tuple(foreign_key["referred_columns"])
        for foreign_key in inspector.get_foreign_keys("asset_versions")
    }
    interview_turn_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): tuple(
            foreign_key["referred_columns"]
        )
        for foreign_key in inspector.get_foreign_keys("interview_turns")
    }
    interview_operation_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): tuple(
            foreign_key["referred_columns"]
        )
        for foreign_key in inspector.get_foreign_keys("interview_operations")
    }
    interview_proposal_foreign_keys = {
        tuple(foreign_key["constrained_columns"]): tuple(
            foreign_key["referred_columns"]
        )
        for foreign_key in inspector.get_foreign_keys("interview_proposals")
    }
    accepted_design_foreign_key = next(
        foreign_key
        for foreign_key in inspector.get_foreign_keys("interview_proposals")
        if tuple(foreign_key["constrained_columns"])
        == ("organization_id", "accepted_design_id")
    )
    approval_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("approvals")
    }
    audit_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("audit_events")
    }
    build_job_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("build_jobs")
    }
    asset_version_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("asset_versions")
    }
    interview_operation_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("interview_operations")
    }
    harness_design_unique_constraints = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("harness_designs")
    }

    assert build_job_columns["organization_id"]["nullable"] is False
    assert harness_design_columns["validation_findings_json"]["nullable"] is True
    assert asset_version_columns["organization_id"]["nullable"] is False
    assert build_job_foreign_keys[("organization_id",)] == ("id",)
    assert asset_version_foreign_keys[("organization_id",)] == ("id",)
    assert interview_turn_foreign_keys[
        ("organization_id", "session_id")
    ] == ("organization_id", "id")
    assert interview_turn_foreign_keys[
        ("organization_id", "session_id", "operation_id")
    ] == ("organization_id", "session_id", "id")
    assert interview_operation_foreign_keys[
        ("organization_id", "session_id")
    ] == ("organization_id", "id")
    assert (
        "organization_id",
        "session_id",
        "id",
    ) in interview_operation_unique_constraints
    assert ("organization_id", "id") in harness_design_unique_constraints
    assert interview_proposal_foreign_keys[
        ("organization_id", "session_id")
    ] == ("organization_id", "id")
    assert interview_proposal_foreign_keys[
        ("organization_id", "accepted_design_id")
    ] == ("organization_id", "id")
    assert accepted_design_foreign_key["referred_table"] == "harness_designs"
    assert accepted_design_foreign_key["options"]["ondelete"] == "RESTRICT"
    assert build_job_indexes["ix_build_jobs_organization_id"] == ("organization_id",)
    assert (
        asset_version_indexes["ix_asset_versions_organization_id"]
        == ("organization_id",)
    )
    assert approval_indexes["ix_approvals_subject"] == (
        "organization_id",
        "subject_type",
        "subject_id",
    )
    assert audit_indexes["ix_audit_events_resource"] == (
        "organization_id",
        "resource_type",
        "resource_id",
    )


def test_interview_turn_operation_fk_rejects_cross_tenant_reference_and_isolates_cascade():
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    def stored_session(organization_id: str, session_id: str) -> InterviewSession:
        return InterviewSession(
            id=session_id,
            organization_id=organization_id,
            owner_subject_id="author",
            name="Interview",
            customer_id=organization_id,
            revision=0,
            status="active",
            consent_version="2026-09-15",
            consented_at=now,
            stage="discovery",
            selected_scope=None,
            proposed_evidence_json=[],
            confirmed_evidence_json=[],
            creation_request_id=str(uuid4()),
            creation_input_digest="a" * 64,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(days=30),
        )

    with Session(engine) as db:
        db.add_all(
            [
                Organization(
                    id="org-a",
                    entra_tenant_id="tenant-a",
                    name="A",
                ),
                Organization(
                    id="org-b",
                    entra_tenant_id="tenant-b",
                    name="B",
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                stored_session("org-a", "session-a"),
                stored_session("org-b", "session-b"),
            ]
        )
        db.flush()
        operation_a = InterviewOperation(
            id="operation-a",
            organization_id="org-a",
            session_id="session-a",
            request_id=str(uuid4()),
            kind="answer",
            input_digest="b" * 64,
            status="succeeded",
            ownership_token=str(uuid4()),
            base_revision=0,
            lease_expires_at=now,
            created_at=now,
            updated_at=now,
        )
        operation_b = InterviewOperation(
            id="operation-b",
            organization_id="org-b",
            session_id="session-b",
            request_id=str(uuid4()),
            kind="answer",
            input_digest="c" * 64,
            status="succeeded",
            ownership_token=str(uuid4()),
            base_revision=0,
            lease_expires_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add_all([operation_a, operation_b])
        db.flush()
        db.add(
            InterviewTurn(
                id="turn-b",
                organization_id="org-b",
                session_id="session-b",
                operation_id="operation-b",
                sequence=1,
                role="assistant",
                text="B",
                created_at=now,
            )
        )
        db.commit()

        db.add(
            InterviewTurn(
                id="cross-tenant-turn",
                organization_id="org-a",
                session_id="session-a",
                operation_id="operation-b",
                sequence=1,
                role="assistant",
                text="invalid",
                created_at=now,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.delete(db.get(InterviewSession, "session-a"))
        db.commit()
        assert db.get(InterviewTurn, "turn-b") is not None


def test_accepted_design_fk_rejects_invalid_links_and_preserves_design_lifecycle():
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    def stored_session(
        organization_id: str,
        session_id: str,
        *,
        expires_at: datetime,
    ) -> InterviewSession:
        return InterviewSession(
            id=session_id,
            organization_id=organization_id,
            owner_subject_id="author",
            name="Interview",
            customer_id=organization_id,
            revision=1,
            status="completed",
            consent_version="2026-09-15",
            consented_at=now,
            stage="summary",
            selected_scope="issue-to-reviewed-pr",
            proposed_evidence_json=[],
            confirmed_evidence_json=[],
            creation_request_id=str(uuid4()),
            creation_input_digest="a" * 64,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

    def design(organization_id: str, design_id: str) -> HarnessDesign:
        return HarnessDesign(
            id=design_id,
            organization_id=organization_id,
            customer_id=organization_id,
            name="Design",
            profile_json={},
            workflow_json={},
            scenarios_json=[],
            catalog_json={},
            revision=1,
            digest="d" * 64,
            status="draft",
            created_by="author",
            created_at=now,
            updated_at=now,
        )

    def proposal(
        organization_id: str,
        session_id: str,
        proposal_id: str,
        accepted_design_id: str,
    ) -> InterviewProposal:
        return InterviewProposal(
            id=proposal_id,
            organization_id=organization_id,
            session_id=session_id,
            revision=1,
            digest="e" * 64,
            status="accepted",
            candidate_json={},
            findings_json=[],
            accepted_design_id=accepted_design_id,
            created_at=now,
            updated_at=now,
        )

    with Session(engine) as db:
        db.add_all(
            [
                Organization(id="org-a", entra_tenant_id="tenant-a", name="A"),
                Organization(id="org-b", entra_tenant_id="tenant-b", name="B"),
            ]
        )
        db.flush()
        db.add_all(
            [
                stored_session(
                    "org-a",
                    "session-a",
                    expires_at=now + timedelta(days=1),
                ),
                stored_session(
                    "org-b",
                    "session-b",
                    expires_at=now + timedelta(days=1),
                ),
                design("org-a", "design-a"),
                design("org-b", "design-b"),
            ]
        )
        db.commit()

        db.add(proposal("org-a", "session-a", "cross-tenant", "design-b"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(proposal("org-a", "session-a", "dangling", "missing-design"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.add(proposal("org-a", "session-a", "accepted-a", "design-a"))
        db.commit()
        db.delete(db.get(HarnessDesign, "design-a"))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        db.delete(db.get(InterviewSession, "session-a"))
        db.commit()
        assert db.get(HarnessDesign, "design-a") is not None

        expired_session = stored_session(
            "org-a",
            "expired-session",
            expires_at=now - timedelta(seconds=1),
        )
        expired_design = design("org-a", "expired-design")
        db.add_all([expired_session, expired_design])
        db.flush()
        db.add(
            proposal(
                "org-a",
                "expired-session",
                "expired-proposal",
                "expired-design",
            )
        )
        db.commit()

    assert delete_expired_interviews(sessionmaker(engine), now=now) == 1
    with Session(engine) as db:
        assert db.get(InterviewSession, "expired-session") is None
        assert db.get(HarnessDesign, "expired-design") is not None


def test_alembic_upgrade_from_0002_to_head_and_downgrade_base(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "schema-migration.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = create_alembic_config(database_url)

    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        command.upgrade(config, "0002_validation_findings")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        harness_design_columns = {
            column["name"]: column
            for column in inspector.get_columns("harness_designs")
        }
        build_job_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("build_jobs")
        }
        assert harness_design_columns["validation_findings_json"]["nullable"] is True
        assert (
            "organization_id",
            "design_id",
            "design_digest",
        ) not in build_job_unique_constraints
        engine.dispose()

        command.upgrade(config, "head")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        harness_design_columns = {
            column["name"]: column
            for column in inspector.get_columns("harness_designs")
        }
        build_job_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("build_jobs")
        }
        interview_operation_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(
                "interview_operations"
            )
        }
        interview_turn_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): tuple(
                foreign_key["referred_columns"]
            )
            for foreign_key in inspector.get_foreign_keys("interview_turns")
        }
        interview_proposal_foreign_keys = {
            tuple(foreign_key["constrained_columns"]): tuple(
                foreign_key["referred_columns"]
            )
            for foreign_key in inspector.get_foreign_keys(
                "interview_proposals"
            )
        }
        accepted_design_foreign_key = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys(
                "interview_proposals"
            )
            if tuple(foreign_key["constrained_columns"])
            == ("organization_id", "accepted_design_id")
        )
        harness_design_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints(
                "harness_designs"
            )
        }
        assert harness_design_columns["validation_findings_json"]["nullable"] is True
        assert (
            "organization_id",
            "design_id",
            "design_digest",
        ) in build_job_unique_constraints
        assert (
            "organization_id",
            "session_id",
            "id",
        ) in interview_operation_unique_constraints
        assert interview_turn_foreign_keys[
            ("organization_id", "session_id", "operation_id")
        ] == ("organization_id", "session_id", "id")
        assert ("organization_id", "id") in harness_design_unique_constraints
        assert interview_proposal_foreign_keys[
            ("organization_id", "accepted_design_id")
        ] == ("organization_id", "id")
        assert accepted_design_foreign_key["options"]["ondelete"] == "RESTRICT"
        engine.dispose()

        command.downgrade(config, "0002_validation_findings")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        build_job_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("build_jobs")
        }
        assert (
            "organization_id",
            "design_id",
            "design_digest",
        ) not in build_job_unique_constraints
        engine.dispose()

        command.downgrade(config, "base")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        assert "organizations" not in table_names
        assert "harness_designs" not in table_names
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_alembic_0007_preserves_existing_accepted_proposal_link(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "proposal-design-fk-migration.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = create_alembic_config(database_url)
    now = datetime.now(UTC)

    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        command.upgrade(config, "0006_proposal_acceptance")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, entra_tenant_id, name)
                    VALUES ('org-acme', 'tenant-acme', 'Acme')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO harness_designs (
                        id, organization_id, customer_id, name, profile_json,
                        workflow_json, scenarios_json, catalog_json, revision,
                        digest, status, created_by, created_at, updated_at,
                        validation_findings_json
                    ) VALUES (
                        'design-1', 'org-acme', 'customer-1', 'Design',
                        '{}', '{}', '[]', '{}', 1, :design_digest, 'draft',
                        'author-1', :now, :now, NULL
                    )
                    """
                ),
                {"design_digest": "d" * 64, "now": now},
            )
            connection.execute(
                text(
                    """
                    INSERT INTO interview_sessions (
                        id, organization_id, owner_subject_id, name, customer_id,
                        revision, status, consent_version, consented_at, stage,
                        selected_scope, proposed_evidence_json,
                        confirmed_evidence_json, creation_request_id,
                        creation_input_digest, created_at, updated_at, expires_at
                    ) VALUES (
                        'session-1', 'org-acme', 'author-1', 'Interview',
                        'customer-1', 1, 'completed', '2026-09-15', :now,
                        'summary', 'issue-to-reviewed-pr', '[]', '[]',
                        'creation-request-1', :input_digest, :now, :now, :expires
                    )
                    """
                ),
                {
                    "input_digest": "a" * 64,
                    "now": now,
                    "expires": now + timedelta(days=1),
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO interview_proposals (
                        id, organization_id, session_id, revision, digest,
                        status, candidate_json, findings_json, created_at,
                        updated_at, accepted_design_id
                    ) VALUES (
                        'proposal-1', 'org-acme', 'session-1', 1,
                        :proposal_digest, 'accepted', '{}', '[]', :now, :now,
                        'design-1'
                    )
                    """
                ),
                {"proposal_digest": "e" * 64, "now": now},
            )
        engine.dispose()

        command.upgrade(config, "head")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        assert ("organization_id", "id") in {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("harness_designs")
        }
        accepted_design_foreign_key = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys(
                "interview_proposals"
            )
            if tuple(foreign_key["constrained_columns"])
            == ("organization_id", "accepted_design_id")
        )
        assert accepted_design_foreign_key["options"]["ondelete"] == "RESTRICT"
        with engine.begin() as connection:
            assert connection.scalar(
                text(
                    """
                    SELECT COUNT(*) FROM interview_proposals
                    WHERE id = 'proposal-1' AND accepted_design_id = 'design-1'
                    """
                )
            ) == 1
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_alembic_upgrade_from_0002_collapses_duplicate_build_job_identities(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "schema-migration-duplicates.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = create_alembic_config(database_url)
    duplicate_identity = {
        "organization_id": "org-acme",
        "design_id": "design-1",
        "design_digest": "d" * 64,
    }
    status_rank_identity = {
        "organization_id": "org-acme",
        "design_id": "design-2",
        "design_digest": "e" * 64,
    }
    tie_break_identity = {
        "organization_id": "org-acme",
        "design_id": "design-3",
        "design_digest": "f" * 64,
    }

    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        command.upgrade(config, "0002_validation_findings")

        engine = create_engine(database_url)
        with engine.begin() as connection:
            created_at = datetime(2026, 9, 14, 13, 0, tzinfo=UTC)
            connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, entra_tenant_id, name)
                    VALUES (:id, :entra_tenant_id, :name)
                    """
                ),
                {
                    "id": "org-acme",
                    "entra_tenant_id": "tenant-acme",
                    "name": "Acme",
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO harness_designs (
                        id,
                        organization_id,
                        customer_id,
                        name,
                        profile_json,
                        workflow_json,
                        scenarios_json,
                        catalog_json,
                        revision,
                        digest,
                        status,
                        created_by,
                        created_at,
                        updated_at,
                        validation_findings_json
                    ) VALUES (
                        :id,
                        :organization_id,
                        :customer_id,
                        :name,
                        :profile_json,
                        :workflow_json,
                        :scenarios_json,
                        :catalog_json,
                        :revision,
                        :digest,
                        :status,
                        :created_by,
                        :created_at,
                        :updated_at,
                        :validation_findings_json
                    )
                    """
                ),
                [
                    {
                        "id": "design-1",
                        "organization_id": "org-acme",
                        "customer_id": "customer-1",
                        "name": "Design 1",
                        "profile_json": "{}",
                        "workflow_json": "{}",
                        "scenarios_json": "[]",
                        "catalog_json": "{}",
                        "revision": 1,
                        "digest": duplicate_identity["design_digest"],
                        "status": "approved",
                        "created_by": "author-1",
                        "created_at": created_at,
                        "updated_at": created_at,
                        "validation_findings_json": None,
                    },
                    {
                        "id": "design-2",
                        "organization_id": "org-acme",
                        "customer_id": "customer-2",
                        "name": "Design 2",
                        "profile_json": "{}",
                        "workflow_json": "{}",
                        "scenarios_json": "[]",
                        "catalog_json": "{}",
                        "revision": 1,
                        "digest": status_rank_identity["design_digest"],
                        "status": "approved",
                        "created_by": "author-1",
                        "created_at": created_at,
                        "updated_at": created_at,
                        "validation_findings_json": None,
                    },
                    {
                        "id": "design-3",
                        "organization_id": "org-acme",
                        "customer_id": "customer-3",
                        "name": "Design 3",
                        "profile_json": "{}",
                        "workflow_json": "{}",
                        "scenarios_json": "[]",
                        "catalog_json": "{}",
                        "revision": 1,
                        "digest": tie_break_identity["design_digest"],
                        "status": "approved",
                        "created_by": "author-1",
                        "created_at": created_at,
                        "updated_at": created_at,
                        "validation_findings_json": None,
                    },
                ],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO build_jobs (
                        id,
                        organization_id,
                        design_id,
                        design_digest,
                        status,
                        attempts,
                        artifact_key,
                        artifact_digest,
                        error_code,
                        created_at,
                        started_at,
                        finished_at,
                        updated_at
                    ) VALUES (
                        :id,
                        :organization_id,
                        :design_id,
                        :design_digest,
                        :status,
                        :attempts,
                        :artifact_key,
                        :artifact_digest,
                        :error_code,
                        :created_at,
                        :started_at,
                        :finished_at,
                        :updated_at
                    )
                    """
                ),
                [
                    {
                        "id": "build-failed",
                        **duplicate_identity,
                        "status": "failed",
                        "attempts": 1,
                        "artifact_key": None,
                        "artifact_digest": None,
                        "error_code": "worker-failed",
                        "created_at": datetime(2026, 9, 14, 13, 0, tzinfo=UTC),
                        "started_at": None,
                        "finished_at": None,
                        "updated_at": datetime(2026, 9, 14, 13, 1, tzinfo=UTC),
                    },
                    {
                        "id": "build-queued",
                        **duplicate_identity,
                        "status": "queued",
                        "attempts": 1,
                        "artifact_key": None,
                        "artifact_digest": None,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 2, tzinfo=UTC),
                        "started_at": None,
                        "finished_at": None,
                        "updated_at": datetime(2026, 9, 14, 13, 3, tzinfo=UTC),
                    },
                    {
                        "id": "build-running",
                        **duplicate_identity,
                        "status": "running",
                        "attempts": 2,
                        "artifact_key": None,
                        "artifact_digest": None,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 4, tzinfo=UTC),
                        "started_at": datetime(2026, 9, 14, 13, 4, tzinfo=UTC),
                        "finished_at": None,
                        "updated_at": datetime(2026, 9, 14, 13, 5, tzinfo=UTC),
                    },
                    {
                        "id": "build-succeeded-older",
                        **duplicate_identity,
                        "status": "succeeded",
                        "attempts": 1,
                        "artifact_key": "artifacts/older.tar",
                        "artifact_digest": "a" * 64,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 6, tzinfo=UTC),
                        "started_at": datetime(2026, 9, 14, 13, 6, tzinfo=UTC),
                        "finished_at": datetime(2026, 9, 14, 13, 7, tzinfo=UTC),
                        "updated_at": datetime(2026, 9, 14, 13, 7, tzinfo=UTC),
                    },
                    {
                        "id": "build-succeeded-newer",
                        **duplicate_identity,
                        "status": "succeeded",
                        "attempts": 3,
                        "artifact_key": "artifacts/newer.tar",
                        "artifact_digest": "b" * 64,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 8, tzinfo=UTC),
                        "started_at": datetime(2026, 9, 14, 13, 8, tzinfo=UTC),
                        "finished_at": datetime(2026, 9, 14, 13, 9, tzinfo=UTC),
                        "updated_at": datetime(2026, 9, 14, 13, 9, tzinfo=UTC),
                    },
                    {
                        "id": "build-status-running",
                        **status_rank_identity,
                        "status": "running",
                        "attempts": 1,
                        "artifact_key": None,
                        "artifact_digest": None,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 20, tzinfo=UTC),
                        "started_at": datetime(2026, 9, 14, 13, 20, tzinfo=UTC),
                        "finished_at": None,
                        "updated_at": datetime(2026, 9, 14, 13, 20, tzinfo=UTC),
                    },
                    {
                        "id": "build-status-succeeded",
                        **status_rank_identity,
                        "status": "succeeded",
                        "attempts": 1,
                        "artifact_key": "artifacts/status.tar",
                        "artifact_digest": "c" * 64,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 10, tzinfo=UTC),
                        "started_at": datetime(2026, 9, 14, 13, 10, tzinfo=UTC),
                        "finished_at": datetime(2026, 9, 14, 13, 11, tzinfo=UTC),
                        "updated_at": datetime(2026, 9, 14, 13, 11, tzinfo=UTC),
                    },
                    {
                        "id": "build-tie-b",
                        **tie_break_identity,
                        "status": "queued",
                        "attempts": 1,
                        "artifact_key": None,
                        "artifact_digest": None,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 30, tzinfo=UTC),
                        "started_at": None,
                        "finished_at": None,
                        "updated_at": datetime(2026, 9, 14, 13, 31, tzinfo=UTC),
                    },
                    {
                        "id": "build-tie-a",
                        **tie_break_identity,
                        "status": "queued",
                        "attempts": 2,
                        "artifact_key": None,
                        "artifact_digest": None,
                        "error_code": None,
                        "created_at": datetime(2026, 9, 14, 13, 30, tzinfo=UTC),
                        "started_at": None,
                        "finished_at": None,
                        "updated_at": datetime(2026, 9, 14, 13, 31, tzinfo=UTC),
                    },
                ],
            )
        engine.dispose()

        command.upgrade(config, "head")

        engine = create_engine(database_url)
        with engine.connect() as connection:
            survivor_rows = connection.execute(
                text(
                    """
                    SELECT id, status, artifact_key
                    FROM build_jobs
                    ORDER BY design_id, id
                    """
                )
            ).mappings().all()
            identity_counts = connection.execute(
                text(
                    """
                    SELECT organization_id, design_id, design_digest, COUNT(*) AS row_count
                    FROM build_jobs
                    GROUP BY organization_id, design_id, design_digest
                    ORDER BY design_id
                    """
                )
            ).mappings().all()

        inspector = inspect(engine)
        build_job_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("build_jobs")
        }

        assert survivor_rows == [
            {
                "id": "build-succeeded-newer",
                "status": "succeeded",
                "artifact_key": "artifacts/newer.tar",
            },
            {
                "id": "build-status-succeeded",
                "status": "succeeded",
                "artifact_key": "artifacts/status.tar",
            },
            {
                "id": "build-tie-a",
                "status": "queued",
                "artifact_key": None,
            },
        ]
        assert [row["row_count"] for row in identity_counts] == [1, 1, 1]
        assert (
            "organization_id",
            "design_id",
            "design_digest",
        ) in build_job_unique_constraints

        with Session(engine) as session:
            session.add(
                BuildJob(
                    id="build-after-upgrade",
                    **duplicate_identity,
                    status="queued",
                    attempts=1,
                    artifact_key=None,
                    artifact_digest=None,
                    error_code=None,
                    created_at=datetime(2026, 9, 14, 14, 0, tzinfo=UTC),
                    started_at=None,
                    finished_at=None,
                    updated_at=datetime(2026, 9, 14, 14, 0, tzinfo=UTC),
                )
            )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
            else:
                raise AssertionError("expected duplicate identity to violate uniqueness")
        engine.dispose()

        command.downgrade(config, "0002_validation_findings")

        engine = create_engine(database_url)
        with Session(engine) as session:
            session.add(
                BuildJob(
                    id="build-after-downgrade",
                    **duplicate_identity,
                    status="failed",
                    attempts=2,
                    artifact_key=None,
                    artifact_digest=None,
                    error_code="worker-failed",
                    created_at=datetime(2026, 9, 14, 14, 1, tzinfo=UTC),
                    started_at=None,
                    finished_at=None,
                    updated_at=datetime(2026, 9, 14, 14, 1, tzinfo=UTC),
                )
            )
            session.commit()
            duplicate_count = session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM build_jobs
                    WHERE organization_id = :organization_id
                      AND design_id = :design_id
                      AND design_digest = :design_digest
                    """
                ),
                duplicate_identity,
            ).scalar_one()

        inspector = inspect(engine)
        downgraded_build_job_unique_constraints = {
            tuple(constraint["column_names"])
            for constraint in inspector.get_unique_constraints("build_jobs")
        }

        assert duplicate_count == 2
        assert (
            "organization_id",
            "design_id",
            "design_digest",
        ) not in downgraded_build_job_unique_constraints
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_asset_slug_is_unique_within_an_organization():
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
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

        session.add(
            Asset(
                id="asset-1",
                organization_id="org-acme",
                kind="skill",
                slug="release-flow",
                name="Release Flow",
                description="Internal workflow",
                owner_subject_id="user-1",
                visibility="internal",
                lifecycle="active",
            )
        )
        session.commit()

        session.add(
            Asset(
                id="asset-2",
                organization_id="org-acme",
                kind="workflow",
                slug="release-flow",
                name="Same Tenant Slug",
                description="Duplicate slug in same org",
                owner_subject_id="user-2",
                visibility="internal",
                lifecycle="active",
            )
        )

        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("expected duplicate slug to violate uniqueness")

        session.add(
            Asset(
                id="asset-3",
                organization_id="org-umbrella",
                kind="workflow",
                slug="release-flow",
                name="Cross Tenant Slug",
                description="Same slug in different org",
                owner_subject_id="user-3",
                visibility="internal",
                lifecycle="active",
            )
        )
        session.commit()


def test_tenant_owned_build_jobs_and_asset_versions_require_organization_ids():
    engine = create_sqlite_engine()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            Organization(
                id="org-acme",
                entra_tenant_id="tenant-acme",
                name="Acme",
            )
        )
        session.commit()

        session.add(
            HarnessDesign(
                id="design-1",
                organization_id="org-acme",
                customer_id="customer-1",
                name="Draft Design",
                profile_json={"name": "profile"},
                workflow_json={"steps": []},
                scenarios_json=[],
                catalog_json={"items": []},
                validation_findings_json=None,
                revision=1,
                digest="d" * 64,
                status="draft",
                created_by="user-1",
            )
        )
        session.add(
            Asset(
                id="asset-1",
                organization_id="org-acme",
                kind="skill",
                slug="release-flow",
                name="Release Flow",
                description="Internal workflow",
                owner_subject_id="user-1",
                visibility="internal",
                lifecycle="active",
            )
        )
        session.commit()

        session.add(
            BuildJob(
                id="build-1",
                organization_id="org-acme",
                design_id="design-1",
                design_digest="d" * 64,
                status="queued",
                attempts=0,
            )
        )
        session.add(
            AssetVersion(
                id="asset-version-1",
                organization_id="org-acme",
                asset_id="asset-1",
                version="1.0.0",
                manifest_json={"entrypoint": "release-flow"},
                digest="a" * 64,
                artifact_key="artifacts/release-flow-1.0.0.tgz",
                artifact_digest="b" * 64,
                status="draft",
                channel="internal",
                created_by="user-1",
            )
        )
        session.commit()


def test_alembic_0004_deprecates_duplicate_published_channel_versions(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "published-channel.db"
    database_url = f"sqlite+pysqlite:///{database_path}"
    config = create_alembic_config(database_url)

    monkeypatch.setenv("HF_DATABASE_URL", database_url)
    get_settings.cache_clear()

    try:
        command.upgrade(config, "0003_build_identity")

        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO organizations (id, entra_tenant_id, name)
                    VALUES ('org-acme', 'tenant-acme', 'Acme')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO assets (
                        id, organization_id, kind, slug, name, description,
                        owner_subject_id, visibility, lifecycle,
                        created_at, updated_at
                    ) VALUES (
                        'asset-1', 'org-acme', 'workflow', 'issue-to-pr', 'Issue',
                        'desc', 'owner-1', 'internal', 'active',
                        :created_at, :updated_at
                    )
                    """
                ),
                {
                    "created_at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
                    "updated_at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
                },
            )
            for index, version in enumerate(("1.0.0", "1.0.1", "2.0.0")):
                connection.execute(
                    text(
                        """
                        INSERT INTO asset_versions (
                            id, organization_id, asset_id, version, manifest_json,
                            digest, artifact_key, artifact_digest, status, channel,
                            created_by, created_at, updated_at
                        ) VALUES (
                            :id, 'org-acme', 'asset-1', :version, '{}',
                            :digest, :artifact_key, :artifact_digest, 'published',
                            'stable', 'author-1', :created_at, :updated_at
                        )
                        """
                    ),
                    {
                        "id": f"version-{index}",
                        "version": version,
                        "digest": f"{index}" * 64,
                        "artifact_key": f"key-{index}",
                        "artifact_digest": f"{index}" * 64,
                        "created_at": datetime(2026, 9, 14, 12, index, tzinfo=UTC),
                        "updated_at": datetime(2026, 9, 14, 12, index, tzinfo=UTC),
                    },
                )
        engine.dispose()

        command.upgrade(config, "head")

        engine = create_engine(database_url)
        with engine.connect() as connection:
            statuses = {
                row["id"]: row["status"]
                for row in connection.execute(
                    text("SELECT id, status FROM asset_versions ORDER BY id")
                ).mappings()
            }
        index_names = {
            index["name"] for index in inspect(engine).get_indexes("asset_versions")
        }
        assert statuses == {
            "version-0": "deprecated",
            "version-1": "deprecated",
            "version-2": "published",
        }
        assert "uq_asset_versions_published_channel" in index_names

        with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        UPDATE asset_versions
                        SET status = 'published'
                        WHERE id = 'version-0'
                        """
                    )
                )
        engine.dispose()

        command.downgrade(config, "0003_build_identity")

        engine = create_engine(database_url)
        index_names = {
            index["name"] for index in inspect(engine).get_indexes("asset_versions")
        }
        assert "uq_asset_versions_published_channel" not in index_names
        engine.dispose()
    finally:
        get_settings.cache_clear()
