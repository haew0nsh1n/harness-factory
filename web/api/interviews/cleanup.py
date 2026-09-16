from web.api.config import get_settings
from web.api.db import create_session_factory

from .service import delete_expired_interviews


def main() -> None:
    engine, session_factory = create_session_factory(get_settings())
    try:
        deleted = delete_expired_interviews(session_factory)
        print(f"Deleted {deleted} expired interview session(s).")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
