from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError

from web.api.builds import worker as worker_module
from web.api.config import Settings
from web.api.db import create_session_factory
from web.api.builds.worker import (
    BuildWorker,
    backoff_seconds,
    is_retryable_database_error,
    serve,
)


class StubWorker:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)
        self.calls = 0

    def run_once(self) -> dict[str, object]:
        self.calls += 1
        if not self._results:
            return {"ok": True, "processed": False}
        outcome = self._results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def operational_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("server closed connection"))


def stopper(limit: int):
    state = {"count": 0}

    def should_stop() -> bool:
        state["count"] += 1
        return state["count"] > limit

    return should_stop


def test_operational_errors_are_retryable() -> None:
    assert is_retryable_database_error(operational_error()) is True
    assert (
        is_retryable_database_error(InterfaceError("x", {}, Exception("gone"))) is True
    )


def test_programming_and_integrity_errors_are_not_retryable() -> None:
    integrity = IntegrityError("INSERT", {}, Exception("duplicate"))
    assert is_retryable_database_error(integrity) is False
    assert is_retryable_database_error(TypeError("bug")) is False
    assert is_retryable_database_error(ValueError("bug")) is False


def test_backoff_is_bounded_and_increasing() -> None:
    delays = [backoff_seconds(attempt) for attempt in range(1, 12)]

    assert delays[0] == 0.5
    assert delays == sorted(delays)
    assert max(delays) <= 30.0


def test_serve_retries_connection_errors_and_recovers() -> None:
    worker = StubWorker(
        [
            operational_error(),
            operational_error(),
            {"ok": True, "processed": True, "build_id": "b1", "status": "succeeded"},
        ]
    )
    slept: list[float] = []

    exit_code = serve(worker, should_stop=stopper(4), sleep=slept.append)

    assert exit_code == 0
    assert worker.calls == 4
    assert slept[:2] == [0.5, 1.0]


def test_serve_gives_up_after_bounded_retries() -> None:
    worker = StubWorker([operational_error() for _ in range(10)])
    slept: list[float] = []

    exit_code = serve(
        worker,
        should_stop=stopper(20),
        sleep=slept.append,
        max_connection_retries=3,
    )

    assert exit_code == 1
    assert worker.calls == 4
    assert len(slept) == 3


def test_serve_reraises_programming_errors() -> None:
    worker = StubWorker([TypeError("programming error")])

    with pytest.raises(TypeError):
        serve(worker, should_stop=stopper(5), sleep=lambda _: None)

    assert worker.calls == 1


def test_serve_sleeps_when_idle() -> None:
    worker = StubWorker([])
    slept: list[float] = []

    serve(worker, should_stop=stopper(2), sleep=slept.append)

    assert slept == [worker_module.IDLE_SLEEP_SECONDS] * 2


def test_worker_reuses_one_engine_across_iterations(tmp_path, monkeypatch) -> None:
    from sqlalchemy import create_engine

    from web.api.config import Settings
    from web.api.db import Base

    database_url = f"sqlite+pysqlite:///{tmp_path / 'reuse.db'}"
    setup_engine = create_engine(database_url)
    Base.metadata.create_all(setup_engine)
    setup_engine.dispose()

    engines: list[object] = []
    original_factory = worker_module.create_session_factory

    def counting_factory(settings=None):
        engine, factory = original_factory(settings)
        engines.append(engine)
        return engine, factory

    monkeypatch.setattr(worker_module, "create_session_factory", counting_factory)

    worker = BuildWorker(
        Settings(
            auth_mode="development",
            allow_insecure_development_auth=True,
            database_url=database_url,
            artifact_root=tmp_path / "artifacts",
        )
    )
    try:
        serve(worker, should_stop=stopper(3), sleep=lambda _: None)
    finally:
        worker.dispose()

    assert len(engines) == 1


def test_non_sqlite_engines_use_pool_pre_ping():
    settings = Settings(
        database_url="postgresql+psycopg://hf:hf@127.0.0.1:5432/harness_factory",
        artifact_root="artifacts-unused",
    )
    engine, _factory = create_session_factory(settings)
    try:
        assert engine.pool._pre_ping is True
    finally:
        engine.dispose()
