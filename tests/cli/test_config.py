from __future__ import annotations

import json
import stat

import pytest

from hf_cli.config import (
    DevelopmentIdentity,
    RegistryConfig,
    load_config,
    save_config,
    validate_registry_url,
)
from hf_cli.errors import CliError


def test_production_registry_requires_https_origin_without_credentials() -> None:
    with pytest.raises(CliError, match="HTTPS"):
        validate_registry_url("http://registry.example.test", development=False)
    with pytest.raises(CliError, match="credentials"):
        validate_registry_url(
            "https://user:password@registry.example.test", development=False
        )
    with pytest.raises(CliError, match="origin"):
        validate_registry_url(
            "https://registry.example.test/api?token=secret", development=False
        )

    assert (
        validate_registry_url("https://registry.example.test/", development=False)
        == "https://registry.example.test"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000",
        "http://[::1]:8000",
        "https://127.0.0.1:8443",
    ],
)
def test_development_registry_accepts_only_literal_loopback_origins(url: str) -> None:
    assert validate_registry_url(url, development=True) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000",
        "http://192.168.1.2:8000",
        "https://registry.example.test",
        "http://127.0.0.1:8000/path",
    ],
)
def test_development_registry_rejects_non_literal_loopback_or_non_origin(
    url: str,
) -> None:
    with pytest.raises(CliError, match="loopback|origin"):
        validate_registry_url(url, development=True)


def test_config_round_trip_is_owner_only_and_contains_no_tokens(tmp_path) -> None:
    path = tmp_path / "config.json"
    config = RegistryConfig(
        url="https://registry.example.test",
        tenant_id="tenant-1",
        client_id="client-1",
        scope="api://registry/access",
    )

    save_config(config, path=path)

    assert load_config(path=path) == config
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    payload = json.loads(path.read_text())
    assert payload == {
        "url": "https://registry.example.test",
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "scope": "api://registry/access",
        "development": False,
    }
    assert "token" not in path.read_text().lower()


def test_development_identity_round_trips_as_non_secret_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    config = RegistryConfig(
        url="http://127.0.0.1:8000",
        tenant_id="development",
        client_id="development",
        scope="development",
        development=True,
    )
    identity = DevelopmentIdentity(
        organization="org-acme",
        subject="developer-1",
        roles=("developer", "org-admin"),
    )

    save_config(config, development_identity=identity, path=path)
    loaded, loaded_identity = load_config(path=path, include_development_identity=True)

    assert loaded == config
    assert loaded_identity == identity


def test_missing_or_invalid_config_is_a_typed_safe_error(tmp_path) -> None:
    path = tmp_path / "config.json"
    with pytest.raises(CliError) as missing:
        load_config(path=path)
    assert missing.value.code == "not_configured"

    path.write_text('{"url":"https://registry.example.test","access_token":"secret"}')
    with pytest.raises(CliError) as invalid:
        load_config(path=path)
    assert invalid.value.code == "invalid_config"
    assert "secret" not in str(invalid.value)
