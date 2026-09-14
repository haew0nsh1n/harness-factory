from pydantic import ValidationError

from web.api.config import Settings


def test_settings_accepts_known_auth_modes() -> None:
    assert Settings(auth_mode="development").auth_mode == "development"
    assert Settings(auth_mode="entra").auth_mode == "entra"


def test_settings_rejects_typo_in_auth_mode() -> None:
    try:
        Settings(auth_mode="develompent")
    except ValidationError as exc:
        assert "auth_mode" in str(exc)
    else:
        raise AssertionError("expected Settings to reject invalid auth_mode")
