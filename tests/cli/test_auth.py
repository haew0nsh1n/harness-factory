from __future__ import annotations

from dataclasses import dataclass

import pytest
from keyring.errors import KeyringError, PasswordDeleteError, PasswordSetError
from requests.exceptions import RequestException

from hf_cli import auth as auth_module
from hf_cli.auth import AuthSession
from hf_cli.config import DevelopmentIdentity, RegistryConfig
from hf_cli.errors import CliError


class Keyring:
    __module__ = "keyring.backends.macOS"

    def __init__(
        self,
        *,
        get_error: BaseException | None = None,
        set_error: BaseException | None = None,
        delete_error: BaseException | None = None,
    ) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.get_error = get_error
        self.set_error = set_error
        self.delete_error = delete_error

    def get_password(self, service: str, username: str) -> str | None:
        if self.get_error:
            raise self.get_error
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        if self.set_error:
            raise self.set_error
        self.values[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if self.delete_error:
            raise self.delete_error
        if (service, username) not in self.values:
            raise PasswordDeleteError("missing")
        del self.values[(service, username)]


class NullKeyring(Keyring):
    __module__ = "keyring.backends.null"


class PlaintextKeyring(Keyring):
    __module__ = "keyrings.alt.file"


@dataclass
class FakeCache:
    state: str = ""
    has_state_changed: bool = False
    deserialize_error: BaseException | None = None

    def deserialize(self, state: str) -> None:
        if self.deserialize_error:
            raise self.deserialize_error
        self.state = state

    def serialize(self) -> str:
        return self.state or "serialized-cache"


class FakeMsalApp:
    def __init__(
        self,
        *,
        accounts: list[dict[str, str]] | None = None,
        silent_result: dict[str, str] | None = None,
        device_result: dict[str, object] | None = None,
        silent_error: BaseException | None = None,
        initiate_error: BaseException | None = None,
        device_error: BaseException | None = None,
    ) -> None:
        self.accounts = accounts or []
        self.silent_result = silent_result
        self.device_result = device_result or {"access_token": "device-token"}
        self.silent_error = silent_error
        self.initiate_error = initiate_error
        self.device_error = device_error
        self.removed: list[dict[str, str]] = []
        self.device_timeout: int | None = None
        self.silent_accounts: list[dict[str, str]] = []

    def get_accounts(self) -> list[dict[str, str]]:
        return self.accounts

    def acquire_token_silent(self, scopes, account):
        if self.silent_error:
            raise self.silent_error
        assert scopes == ["api://registry/access"]
        self.silent_accounts.append(account)
        return self.silent_result

    def initiate_device_flow(self, scopes):
        if self.initiate_error:
            raise self.initiate_error
        assert scopes == ["api://registry/access"]
        return {
            "user_code": "ABCD-EFGH",
            "verification_uri": "https://microsoft.com/devicelogin",
            "message": "Use code ABCD-EFGH",
            "expires_in": 900,
        }

    def acquire_token_by_device_flow(self, flow, **kwargs):
        if self.device_error:
            raise self.device_error
        assert flow["user_code"] == "ABCD-EFGH"
        self.device_timeout = kwargs["timeout"]
        return self.device_result

    def remove_account(self, account) -> None:
        self.removed.append(account)


def production_config(**changes) -> RegistryConfig:
    values = {
        "url": "https://registry.example.test",
        "tenant_id": "tenant-1",
        "client_id": "client-1",
        "scope": "api://registry/access",
    }
    values.update(changes)
    return RegistryConfig(**values)


def make_session(
    *,
    config: RegistryConfig | None = None,
    keyring_backend=None,
    app: FakeMsalApp | None = None,
    cache: FakeCache | None = None,
    messages: list[str] | None = None,
) -> AuthSession:
    app = app or FakeMsalApp()
    cache = cache or FakeCache()
    return AuthSession(
        config or production_config(),
        keyring_backend=keyring_backend or Keyring(),
        cache_factory=lambda: cache,
        app_factory=lambda **kwargs: app,
        notifier=messages.append if messages is not None else lambda message: None,
        device_flow_timeout=42,
    )


@pytest.mark.parametrize("backend", [NullKeyring(), PlaintextKeyring()])
def test_production_auth_rejects_non_native_keyrings(backend) -> None:
    with pytest.raises(CliError, match="native OS keyring") as error:
        make_session(keyring_backend=backend)
    assert error.value.code == "unsafe_keyring"


def test_keyring_backend_selection_does_not_swallow_type_error(monkeypatch) -> None:
    def get_keyring():
        raise TypeError("bug")

    monkeypatch.setattr("keyring.get_keyring", get_keyring)

    with pytest.raises(TypeError, match="bug"):
        AuthSession(
            production_config(),
            cache_factory=FakeCache,
            app_factory=lambda **kwargs: FakeMsalApp(),
        )


def test_cache_key_isolated_by_registry_tenant_client_and_scope() -> None:
    sessions = [
        make_session(config=production_config()),
        make_session(config=production_config(url="https://other.example.test")),
        make_session(config=production_config(tenant_id="tenant-2")),
        make_session(config=production_config(client_id="client-2")),
        make_session(config=production_config(scope="api://registry/other")),
    ]

    assert len({session.cache_key for session in sessions}) == len(sessions)
    assert all("api://registry/access" not in session.cache_key for session in sessions)


def test_invalid_cached_session_is_typed_and_safe() -> None:
    config = production_config()
    keyring_backend = Keyring()
    location = (
        auth_module.KEYRING_SERVICE,
        auth_module._cache_key(config),
    )
    keyring_backend.values[location] = "cached-secret"

    with pytest.raises(CliError) as error:
        AuthSession(
            config,
            keyring_backend=keyring_backend,
            cache_factory=lambda: FakeCache(
                deserialize_error=ValueError("invalid cache with secret")
            ),
            app_factory=lambda **kwargs: FakeMsalApp(),
        )

    assert error.value.code == "auth_cache_invalid"
    assert "secret" not in str(error.value)


def test_cache_deserialization_does_not_swallow_type_error() -> None:
    config = production_config()
    keyring_backend = Keyring()
    location = (
        auth_module.KEYRING_SERVICE,
        auth_module._cache_key(config),
    )
    keyring_backend.values[location] = "cached-secret"

    with pytest.raises(TypeError, match="bug"):
        AuthSession(
            config,
            keyring_backend=keyring_backend,
            cache_factory=lambda: FakeCache(deserialize_error=TypeError("bug")),
            app_factory=lambda **kwargs: FakeMsalApp(),
        )


def test_headers_use_silent_refresh_and_persist_changed_cache() -> None:
    keyring_backend = Keyring()
    cache = FakeCache(state="new-cache", has_state_changed=True)
    app = FakeMsalApp(
        accounts=[{"home_account_id": "account-1"}],
        silent_result={"access_token": "silent-token"},
    )
    session = make_session(
        keyring_backend=keyring_backend,
        app=app,
        cache=cache,
    )

    assert session.headers() == {"Authorization": "Bearer silent-token"}
    assert keyring_backend.values[session.keyring_location] == "new-cache"


@pytest.mark.parametrize(
    "existing_accounts",
    [
        [
            {"home_account_id": "old-account"},
            {"home_account_id": "new-account"},
        ],
        [
            {"home_account_id": "new-account"},
            {"home_account_id": "old-account"},
        ],
    ],
)
def test_relogin_replaces_old_cache_and_uses_new_account_regardless_of_old_order(
    existing_accounts,
) -> None:
    keyring_backend = Keyring()
    old_cache = FakeCache(state="old-cache")
    new_cache = FakeCache(state="new-cache", has_state_changed=True)
    old_app = FakeMsalApp(
        accounts=existing_accounts,
        silent_result={"access_token": "old-token"},
    )
    new_app = FakeMsalApp(
        accounts=[{"home_account_id": "new-account"}],
        silent_result={"access_token": "new-token"},
    )
    caches = iter([old_cache, new_cache])
    apps = iter([old_app, new_app])
    session = AuthSession(
        production_config(),
        keyring_backend=keyring_backend,
        cache_factory=lambda: next(caches),
        app_factory=lambda **kwargs: next(apps),
        notifier=lambda message: None,
        device_flow_timeout=42,
    )
    keyring_backend.values[session.keyring_location] = "old-cache"

    session.login()

    assert keyring_backend.values[session.keyring_location] == "new-cache"
    headers = session.headers()
    assert headers["Authorization"].endswith("new-token")
    assert new_app.silent_accounts == [{"home_account_id": "new-account"}]
    assert old_app.silent_accounts == []


def test_failed_relogin_preserves_old_cache_and_active_account() -> None:
    keyring_backend = Keyring()
    old_cache = FakeCache(state="old-cache")
    new_cache = FakeCache(state="failed-cache", has_state_changed=True)
    old_app = FakeMsalApp(
        accounts=[{"home_account_id": "old-account"}],
        silent_result={"access_token": "old-token"},
    )
    failed_app = FakeMsalApp(device_result={"error": "authorization_declined"})
    caches = iter([old_cache, new_cache])
    apps = iter([old_app, failed_app])
    session = AuthSession(
        production_config(),
        keyring_backend=keyring_backend,
        cache_factory=lambda: next(caches),
        app_factory=lambda **kwargs: next(apps),
        notifier=lambda message: None,
        device_flow_timeout=42,
    )
    keyring_backend.values[session.keyring_location] = "old-cache"

    with pytest.raises(CliError, match="denied"):
        session.login()

    assert keyring_backend.values[session.keyring_location] == "old-cache"
    headers = session.headers()
    assert headers["Authorization"].endswith("old-token")
    assert old_app.silent_accounts == [{"home_account_id": "old-account"}]


def test_msal_initialization_uses_bounded_transport() -> None:
    captured: dict[str, object] = {}

    def app_factory(**kwargs):
        captured.update(kwargs)
        return FakeMsalApp()

    AuthSession(
        production_config(),
        keyring_backend=Keyring(),
        cache_factory=FakeCache,
        app_factory=app_factory,
    )

    assert captured["timeout"] == 10


def test_msal_initialization_network_error_is_typed_and_safe() -> None:
    def app_factory(**kwargs):
        raise RequestException("provider response with secret")

    with pytest.raises(CliError) as error:
        AuthSession(
            production_config(),
            keyring_backend=Keyring(),
            cache_factory=FakeCache,
            app_factory=app_factory,
        )

    assert error.value.code == "authentication_unavailable"
    assert "secret" not in str(error.value)


def test_msal_initialization_invalid_config_is_typed_and_safe() -> None:
    def app_factory(**kwargs):
        raise ValueError("invalid tenant with secret")

    with pytest.raises(CliError) as error:
        AuthSession(
            production_config(),
            keyring_backend=Keyring(),
            cache_factory=FakeCache,
            app_factory=app_factory,
        )

    assert error.value.code == "invalid_config"
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("defect", [TypeError("bug"), AssertionError("bug")])
def test_msal_initialization_does_not_swallow_programming_defects(defect) -> None:
    def app_factory(**kwargs):
        raise defect

    with pytest.raises(type(defect), match="bug"):
        AuthSession(
            production_config(),
            keyring_backend=Keyring(),
            cache_factory=FakeCache,
            app_factory=app_factory,
        )


def test_expired_session_is_typed_without_exposing_msal_details() -> None:
    app = FakeMsalApp(
        accounts=[{"home_account_id": "account-1"}],
        silent_result={"error": "interaction_required", "error_description": "secret"},
    )
    session = make_session(app=app)

    with pytest.raises(CliError) as error:
        session.headers()

    assert error.value.code == "session_expired"
    assert "secret" not in str(error.value)


def test_silent_refresh_request_error_is_typed_and_safe() -> None:
    session = make_session(
        app=FakeMsalApp(
            accounts=[{"home_account_id": "account-1"}],
            silent_error=RequestException("provider response with secret"),
        )
    )

    with pytest.raises(CliError) as error:
        session.headers()

    assert error.value.code == "authentication_failed"
    assert "secret" not in str(error.value)


def test_silent_refresh_does_not_swallow_assertion_error() -> None:
    session = make_session(
        app=FakeMsalApp(
            accounts=[{"home_account_id": "account-1"}],
            silent_error=AssertionError("bug"),
        )
    )

    with pytest.raises(AssertionError, match="bug"):
        session.headers()


def test_device_login_reports_safe_instruction_and_uses_timeout() -> None:
    messages: list[str] = []
    app = FakeMsalApp(device_result={"access_token": "device-token"})
    session = make_session(app=app, messages=messages)

    session.login()

    assert messages == ["Use code ABCD-EFGH"]
    assert app.device_timeout == 42
    assert "device-token" not in "\n".join(messages)


@pytest.mark.parametrize("stage", ["initiate", "acquire"])
def test_device_login_request_errors_are_typed_and_safe(stage) -> None:
    error = RequestException("provider response with secret")
    app = FakeMsalApp(
        initiate_error=error if stage == "initiate" else None,
        device_error=error if stage == "acquire" else None,
    )
    session = make_session(app=app)

    with pytest.raises(CliError) as caught:
        session.login()

    assert caught.value.code == "login_failed"
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("stage", ["initiate", "acquire"])
def test_device_login_does_not_swallow_type_error(stage) -> None:
    error = TypeError("bug")
    app = FakeMsalApp(
        initiate_error=error if stage == "initiate" else None,
        device_error=error if stage == "acquire" else None,
    )
    session = make_session(app=app)

    with pytest.raises(TypeError, match="bug"):
        session.login()


@pytest.mark.parametrize(
    ("result", "code"),
    [
        ({"error": "authorization_declined", "error_description": "secret"}, "login_denied"),
        ({"error": "expired_token", "error_description": "secret"}, "login_timeout"),
    ],
)
def test_device_login_maps_denial_and_timeout_to_safe_errors(result, code) -> None:
    session = make_session(app=FakeMsalApp(device_result=result))

    with pytest.raises(CliError) as error:
        session.login()

    assert error.value.code == code
    assert "secret" not in str(error.value)


def test_logout_removes_accounts_and_cached_credentials() -> None:
    keyring_backend = Keyring()
    app = FakeMsalApp(accounts=[{"home_account_id": "account-1"}])
    session = make_session(keyring_backend=keyring_backend, app=app)
    keyring_backend.values[session.keyring_location] = "cached-secret"

    session.logout()

    assert app.removed == [{"home_account_id": "account-1"}]
    assert session.keyring_location not in keyring_backend.values


def test_remove_saved_session_deletes_invalid_cache_without_msal() -> None:
    keyring_backend = Keyring()
    session = make_session(keyring_backend=keyring_backend)
    keyring_backend.values[session.keyring_location] = "not-valid-msal-json"

    auth_module.remove_saved_session(
        production_config(),
        keyring_backend=keyring_backend,
    )

    assert session.keyring_location not in keyring_backend.values


def test_remove_saved_session_is_idempotent_only_when_entry_is_missing() -> None:
    auth_module.remove_saved_session(
        production_config(),
        keyring_backend=Keyring(),
    )

    with pytest.raises(CliError) as error:
        auth_module.remove_saved_session(
            production_config(),
            keyring_backend=Keyring(
                get_error=KeyringError("store unavailable with secret")
            ),
        )
    assert error.value.code == "keyring_unavailable"
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("defect", [TypeError("bug"), AssertionError("bug")])
def test_keyring_load_does_not_swallow_programming_defects(defect) -> None:
    with pytest.raises(type(defect), match="bug"):
        make_session(keyring_backend=Keyring(get_error=defect))


def test_keyring_delete_error_is_typed_and_safe() -> None:
    keyring_backend = Keyring(
        delete_error=PasswordDeleteError("store unavailable with secret")
    )
    session = make_session(keyring_backend=keyring_backend)
    keyring_backend.values[session.keyring_location] = "cached-secret"

    with pytest.raises(CliError) as error:
        session.logout()

    assert error.value.code == "keyring_unavailable"
    assert "secret" not in str(error.value)


def test_keyring_delete_does_not_swallow_type_error() -> None:
    keyring_backend = Keyring(delete_error=TypeError("bug"))
    session = make_session(keyring_backend=keyring_backend)
    keyring_backend.values[session.keyring_location] = "cached-secret"

    with pytest.raises(TypeError, match="bug"):
        session.logout()


def test_keyring_persist_error_is_typed_and_safe() -> None:
    session = make_session(
        keyring_backend=Keyring(
            set_error=PasswordSetError("store unavailable with secret")
        ),
        app=FakeMsalApp(
            accounts=[{"home_account_id": "account-1"}],
            silent_result={"access_token": "silent-token"},
        ),
        cache=FakeCache(has_state_changed=True),
    )

    with pytest.raises(CliError) as error:
        session.headers()

    assert error.value.code == "keyring_unavailable"
    assert "secret" not in str(error.value)


def test_keyring_persist_does_not_swallow_assertion_error() -> None:
    session = make_session(
        keyring_backend=Keyring(set_error=AssertionError("bug")),
        app=FakeMsalApp(
            accounts=[{"home_account_id": "account-1"}],
            silent_result={"access_token": "silent-token"},
        ),
        cache=FakeCache(has_state_changed=True),
    )

    with pytest.raises(AssertionError, match="bug"):
        session.headers()


def test_development_auth_uses_only_explicit_identity_headers() -> None:
    config = RegistryConfig(
        url="http://127.0.0.1:8000",
        tenant_id="development",
        client_id="development",
        scope="development",
        development=True,
    )
    session = AuthSession(
        config,
        development_identity=DevelopmentIdentity(
            organization="org-acme",
            subject="developer-1",
            roles=("developer",),
        ),
    )

    assert session.headers() == {
        "X-HF-Organization": "org-acme",
        "X-HF-Subject": "developer-1",
        "X-HF-Roles": "developer",
    }
