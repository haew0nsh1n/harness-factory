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


def test_settings_accepts_and_normalizes_https_azure_openai_origin() -> None:
    configured = Settings(
        azure_openai_endpoint="https://proj-aimain.cognitiveservices.azure.com"
    )
    assert (
        configured.azure_openai_endpoint
        == "https://proj-aimain.cognitiveservices.azure.com/"
    )


def test_settings_rejects_unsafe_azure_openai_endpoint() -> None:
    for endpoint in (
        "http://example.test",
        "https://user:password@example.test",
        "https://example.test/openai/v1",
        "https://example.test?api-key=secret",
    ):
        try:
            Settings(azure_openai_endpoint=endpoint)
        except ValidationError as exc:
            assert "azure_openai_endpoint" in str(exc)
        else:
            raise AssertionError(f"expected Settings to reject {endpoint}")
