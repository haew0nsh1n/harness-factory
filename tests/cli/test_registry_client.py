from __future__ import annotations

import json

import httpx
import pytest

from hf_cli.client import RegistryClient
from hf_cli.config import RegistryConfig
from hf_cli.errors import CliError


class FakeAuth:
    def headers(self) -> dict[str, str]:
        return {"Authorization": "Bearer injected-token"}


def config() -> RegistryConfig:
    return RegistryConfig(
        url="https://registry.example.test",
        tenant_id="tenant-1",
        client_id="client-1",
        scope="api://registry/access",
    )


def build_client(handler) -> tuple[RegistryClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def recording_handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    http_client = httpx.Client(
        transport=httpx.MockTransport(recording_handler),
        follow_redirects=False,
        timeout=5.0,
    )
    return RegistryClient(config(), FakeAuth(), http_client=http_client), requests


def test_whoami_returns_server_membership() -> None:
    client, requests = build_client(
        lambda request: httpx.Response(
            200,
            json={
                "ok": True,
                "actor": {
                    "organization_id": "org-acme",
                    "subject_id": "developer-1",
                    "roles": ["developer"],
                },
            },
        )
    )

    assert client.whoami() == {
        "organization_id": "org-acme",
        "subject_id": "developer-1",
        "roles": ["developer"],
    }
    assert requests[0].url.path == "/api/whoami"


def test_search_uses_registry_route_and_returns_items() -> None:
    client, requests = build_client(
        lambda request: httpx.Response(
            200,
            json={"ok": True, "items": [{"slug": "issue-to-pr", "versions": []}]},
        )
    )

    assert client.search("issue to pr") == [
        {"slug": "issue-to-pr", "versions": []}
    ]
    assert requests[0].url.path == "/api/registry/assets"
    assert requests[0].url.params["query"] == "issue to pr"


def test_info_url_encodes_slug_and_selects_semantic_version() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": True,
                "asset": {
                    "slug": "workflow name",
                    "versions": [
                        {"id": "v1", "version": "1.0.0"},
                        {"id": "v2", "version": "2.0.0"},
                    ],
                },
            },
        )

    client, requests = build_client(handler)

    assert client.info("workflow name", "2.0.0") == {
        "slug": "workflow name",
        "versions": [{"id": "v2", "version": "2.0.0"}],
    }
    assert requests[0].url.raw_path == b"/api/registry/assets/workflow%20name"

    with pytest.raises(CliError) as invalid:
        client.info("workflow", "2.0")
    assert invalid.value.code == "invalid_version"


def test_info_reports_missing_version() -> None:
    client, _ = build_client(
        lambda request: httpx.Response(
            200,
            json={"ok": True, "asset": {"slug": "workflow", "versions": []}},
        )
    )

    with pytest.raises(CliError) as error:
        client.info("workflow", "1.0.0")
    assert error.value.code == "not_found"


def test_delivery_returns_lightweight_shared_metadata() -> None:
    payload = {
        "schema_version": 1,
        "organization_id": "org-acme",
        "asset_id": "asset-1",
        "version_id": "version-1",
        "slug": "issue-to-pr",
        "version": "1.0.0",
        "manifest": {"schema_version": 1},
        "manifest_sha256": "a" * 64,
        "artifact_sha256": "b" * 64,
        "artifact_size": 123,
    }
    client, _ = build_client(
        lambda request: httpx.Response(
            200, json={"ok": True, "delivery": payload}
        )
    )

    metadata = client.delivery("version-1")

    assert metadata.version_id == "version-1"
    assert metadata.model_dump(mode="json") == payload
    assert type(metadata).__module__ == "harness_factory.delivery"


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "unauthorized"), (403, "forbidden"), (404, "not_found")],
)
def test_http_auth_and_not_found_errors_are_typed_and_safe(status: int, code: str) -> None:
    client, _ = build_client(
        lambda request: httpx.Response(
            status,
            content=json.dumps(
                {"code": "server-code", "error": "Bearer server-secret"}
            ).encode(),
        )
    )

    with pytest.raises(CliError) as error:
        client.search("workflow")

    assert error.value.code == code
    assert "server-secret" not in str(error.value)


def test_redirects_are_rejected_without_following_location() -> None:
    client, requests = build_client(
        lambda request: httpx.Response(
            302, headers={"Location": "https://evil.example/token"}
        )
    )

    with pytest.raises(CliError) as error:
        client.search("workflow")

    assert error.value.code == "unexpected_redirect"
    assert len(requests) == 1
    assert "evil.example" not in str(error.value)


def test_network_errors_are_typed_and_safe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connect secret", request=request)

    client, _ = build_client(handler)

    with pytest.raises(CliError) as error:
        client.search("workflow")

    assert error.value.code == "network_error"
    assert "secret" not in str(error.value)


def test_cli_search_json_uses_saved_authentication(monkeypatch, capsys) -> None:
    from hf_cli import main as cli_main

    registry_config = config()
    monkeypatch.setattr(
        cli_main,
        "load_config",
        lambda **kwargs: (registry_config, None),
    )
    monkeypatch.setattr(
        cli_main,
        "AuthSession",
        lambda loaded, development_identity=None: FakeAuth(),
    )

    class FakeRegistryClient:
        def __init__(self, loaded, auth) -> None:
            assert loaded == registry_config
            assert isinstance(auth, FakeAuth)

        def search(self, query: str) -> list[dict[str, object]]:
            assert query == "workflow"
            return [{"slug": "issue-to-pr"}]

    monkeypatch.setattr(cli_main, "RegistryClient", FakeRegistryClient)

    assert cli_main.run(["search", "workflow", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "result": [{"slug": "issue-to-pr"}],
    }


def test_cli_json_error_is_typed_and_safe(monkeypatch, capsys) -> None:
    from hf_cli import main as cli_main

    monkeypatch.setattr(
        cli_main,
        "load_config",
        lambda **kwargs: (_ for _ in ()).throw(
            CliError("not_configured", "run hf login")
        ),
    )

    assert cli_main.run(["info", "workflow", "--json"]) == 1
    assert json.loads(capsys.readouterr().err) == {
        "ok": False,
        "error": "run hf login",
        "code": "not_configured",
    }


def test_cli_logout_deletes_saved_session_without_constructing_auth(
    monkeypatch, capsys
) -> None:
    from hf_cli import main as cli_main

    registry_config = config()
    removed: list[object] = []
    monkeypatch.setattr(
        cli_main,
        "load_config",
        lambda **kwargs: (registry_config, None),
    )
    monkeypatch.setattr(
        cli_main,
        "AuthSession",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("logout must not construct AuthSession")
        ),
    )
    monkeypatch.setattr(
        cli_main,
        "remove_saved_session",
        lambda loaded: removed.append(loaded),
    )

    assert cli_main.run(["logout", "--json"]) == 0
    assert removed == [registry_config]
    assert json.loads(capsys.readouterr().out) == {
        "ok": True,
        "result": {"logged_out": True},
    }
