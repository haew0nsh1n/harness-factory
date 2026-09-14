from collections.abc import Generator
from contextlib import contextmanager

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from web.api.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


def import_model_metadata() -> None:
    from web.api.audit import models as audit_models
    from web.api.builds import models as build_models
    from web.api.designs import models as design_models
    from web.api.identity import models as identity_models
    from web.api.organizations import models as organization_models
    from web.api.registry import models as registry_models

    del (
        audit_models,
        build_models,
        design_models,
        identity_models,
        organization_models,
        registry_models,
    )


def create_session_factory(settings: Settings | None = None):
    resolved = settings or get_settings()
    import_model_metadata()
    engine_kwargs: dict[str, object] = {}
    if resolved.database_url == "sqlite+pysqlite:///:memory:":
        engine_kwargs = {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    elif not resolved.database_url.startswith("sqlite"):
        engine_kwargs = {"pool_pre_ping": True}
    engine = create_engine(resolved.database_url, **engine_kwargs)
    _enable_sqlite_foreign_keys(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        del connection_record
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    engine, factory = create_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def get_session(request: Request) -> Generator[Session, None, None]:
    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
