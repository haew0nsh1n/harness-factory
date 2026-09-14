from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session

from web.api.builds.repository import BuildJobRepository
from web.api.builds.service import BuildService
from web.api.builds.storage import FileArtifactStorage
from web.api.config import Settings, get_settings
from web.api.db import create_session_factory

IDLE_SLEEP_SECONDS = 1.0
MAX_CONNECTION_RETRIES = 8
INITIAL_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 30.0

RETRYABLE_DATABASE_ERRORS = (
    OperationalError,
    InterfaceError,
    SQLAlchemyTimeoutError,
)


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def parser() -> argparse.ArgumentParser:
    root = Parser(description="Build approved Harness Factory design artifacts.")
    root.add_argument("--once", action="store_true")
    return root


def is_retryable_database_error(error: BaseException) -> bool:
    """Only connection and operational faults are retried.

    Programming errors, integrity errors and ordinary bugs must surface so a
    defect is never converted into an unbounded retry loop.
    """
    if isinstance(error, RETRYABLE_DATABASE_ERRORS):
        return True
    if isinstance(error, DBAPIError):
        return bool(error.connection_invalidated)
    return False


def backoff_seconds(attempt: int) -> float:
    exponential = INITIAL_BACKOFF_SECONDS * (2 ** max(attempt - 1, 0))
    return min(exponential, MAX_BACKOFF_SECONDS)


class BuildWorker:
    """Owns a single engine and session factory for the worker process."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._engine, self._session_factory = create_session_factory(self._settings)
        self._storage = FileArtifactStorage(self._settings.artifact_root)

    @property
    def settings(self) -> Settings:
        return self._settings

    @contextmanager
    def _session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def run_once(self) -> dict[str, object]:
        with self._session() as session:
            service = BuildService(
                repository=BuildJobRepository(session),
                settings=self._settings,
                storage=self._storage,
            )
            job = service.run_next()
            return {
                "ok": True,
                "processed": job is not None,
                "build_id": None if job is None else job.id,
                "status": None if job is None else job.status,
            }

    def dispose(self) -> None:
        self._engine.dispose()


def _run_once() -> dict[str, object]:
    worker = BuildWorker()
    try:
        return worker.run_once()
    finally:
        worker.dispose()


def _report_failure(error: str, code: str) -> None:
    print(
        json.dumps({"ok": False, "error": error, "code": code}, sort_keys=True),
        file=sys.stderr,
    )


def serve(
    worker: BuildWorker,
    *,
    should_stop: Callable[[], bool],
    sleep: Callable[[float], None] = time.sleep,
    max_connection_retries: int = MAX_CONNECTION_RETRIES,
) -> int:
    consecutive_failures = 0
    while not should_stop():
        try:
            result = worker.run_once()
        except Exception as exc:
            if not is_retryable_database_error(exc):
                raise
            consecutive_failures += 1
            if consecutive_failures > max_connection_retries:
                _report_failure(str(exc), "worker-database-unavailable")
                return 1
            delay = backoff_seconds(consecutive_failures)
            _report_failure(
                f"database unavailable, retrying in {delay:g}s",
                "worker-database-retry",
            )
            sleep(delay)
            continue
        consecutive_failures = 0
        if not result["processed"]:
            sleep(IDLE_SLEEP_SECONDS)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        if args.once:
            print(json.dumps(_run_once(), sort_keys=True))
            return 0

        stopping = False

        def handle_sigterm(signum, frame):
            del signum, frame
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, handle_sigterm)
        worker = BuildWorker()
        try:
            return serve(worker, should_stop=lambda: stopping)
        finally:
            worker.dispose()
    except (ValueError, OSError, UnicodeError) as exc:
        _report_failure(str(exc), "worker-failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
