from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from typing import Any, Protocol

from hf_cli.config import DevelopmentIdentity, RegistryConfig
from hf_cli.errors import CliError

try:
    from keyring.errors import KeyringError as _KeyringError
except ImportError:
    class _KeyringError(Exception):
        pass

try:
    from requests.exceptions import RequestException as _RequestException
except ImportError:
    class _RequestException(Exception):
        pass

KEYRING_SERVICE = "harness-factory-cli"
MSAL_NETWORK_TIMEOUT = 10
_NATIVE_KEYRINGS = {
    ("keyring.backends.macOS", "Keyring"),
    ("keyring.backends.SecretService", "Keyring"),
    ("keyring.backends.Windows", "WinVaultKeyring"),
}


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...

    def set_password(self, service: str, username: str, password: str) -> None: ...

    def delete_password(self, service: str, username: str) -> None: ...


def _cache_key(config: RegistryConfig) -> str:
    return hashlib.sha256(
        "\0".join(
            (
                config.url,
                config.tenant_id,
                config.client_id,
                config.scope,
            )
        ).encode()
    ).hexdigest()


def _require_native_keyring(backend: KeyringBackend) -> None:
    identity = (type(backend).__module__, type(backend).__name__)
    if identity not in _NATIVE_KEYRINGS:
        raise CliError(
            "unsafe_keyring",
            "a supported native OS keyring is required",
        )


def _native_keyring(
    keyring_backend: KeyringBackend | None = None,
) -> KeyringBackend:
    if keyring_backend is None:
        try:
            import keyring
        except ImportError:
            raise CliError(
                "missing_dependency",
                "keyring is required; install the CLI extra",
            ) from None
        try:
            keyring_backend = keyring.get_keyring()
        except (ImportError, AttributeError, RuntimeError, ValueError, _KeyringError):
            raise CliError(
                "unsafe_keyring",
                "a supported native OS keyring is required",
            ) from None
    _require_native_keyring(keyring_backend)
    return keyring_backend


def remove_saved_session(
    config: RegistryConfig,
    *,
    keyring_backend: KeyringBackend | None = None,
) -> None:
    if config.development:
        return
    backend = _native_keyring(keyring_backend)
    location = (KEYRING_SERVICE, _cache_key(config))
    try:
        if backend.get_password(*location) is None:
            return
        backend.delete_password(*location)
    except _KeyringError:
        raise CliError(
            "keyring_unavailable",
            "unable to remove authentication session from the native OS keyring",
        ) from None


class AuthSession:
    def __init__(
        self,
        config: RegistryConfig,
        *,
        development_identity: DevelopmentIdentity | None = None,
        keyring_backend: KeyringBackend | None = None,
        cache_factory: Callable[[], Any] | None = None,
        app_factory: Callable[..., Any] | None = None,
        notifier: Callable[[str], None] = print,
        device_flow_timeout: int = 300,
    ) -> None:
        self.config = config
        self._development_identity = development_identity
        self._notifier = notifier
        self._device_flow_timeout = device_flow_timeout
        self.cache_key = _cache_key(config)
        self.keyring_location = (KEYRING_SERVICE, self.cache_key)
        self._keyring: KeyringBackend | None = None
        self._cache: Any = None
        self._app: Any = None
        self._cache_factory: Callable[[], Any] | None = None
        self._app_factory: Callable[..., Any] | None = None

        if config.development:
            if development_identity is None:
                raise CliError(
                    "invalid_config",
                    "development identity is not configured",
                )
            return

        self._keyring = _native_keyring(keyring_backend)

        if cache_factory is None or app_factory is None:
            try:
                import msal
            except ImportError:
                raise CliError(
                    "missing_dependency",
                    "MSAL is required; install the CLI extra",
                ) from None
            cache_factory = cache_factory or msal.SerializableTokenCache
            app_factory = app_factory or msal.PublicClientApplication

        self._cache_factory = cache_factory
        self._app_factory = app_factory
        self._cache = cache_factory()
        try:
            serialized = self._keyring.get_password(*self.keyring_location)
        except _KeyringError:
            raise CliError(
                "keyring_unavailable",
                "native OS keyring is unavailable",
            ) from None
        if serialized:
            try:
                self._cache.deserialize(serialized)
            except ValueError:
                raise CliError(
                    "auth_cache_invalid",
                    "saved authentication session is invalid; run 'hf logout'",
                ) from None
        self._app = self._create_app(self._cache)

    def _create_app(self, cache: Any) -> Any:
        authority = (
            "https://login.microsoftonline.com/"
            f"{self.config.tenant_id.strip('/')}"
        )
        assert self._app_factory is not None
        try:
            return self._app_factory(
                client_id=self.config.client_id,
                authority=authority,
                token_cache=cache,
                timeout=MSAL_NETWORK_TIMEOUT,
            )
        except _RequestException:
            raise CliError(
                "authentication_unavailable",
                "authentication service is unavailable",
            ) from None
        except ValueError:
            raise CliError(
                "invalid_config",
                "authentication configuration is invalid",
            ) from None

    def headers(self) -> dict[str, str]:
        if self.config.development:
            identity = self._development_identity
            assert identity is not None
            return {
                "X-HF-Organization": identity.organization,
                "X-HF-Subject": identity.subject,
                "X-HF-Roles": ",".join(identity.roles),
            }
        accounts = self._app.get_accounts()
        if not accounts:
            raise CliError(
                "session_expired",
                "authentication session is missing or expired; run 'hf login'",
            )
        try:
            result = self._app.acquire_token_silent(
                [self.config.scope],
                account=accounts[0],
            )
        except _RequestException:
            raise CliError(
                "authentication_failed",
                "unable to refresh authentication session",
            ) from None
        self._persist_cache()
        token = result.get("access_token") if isinstance(result, dict) else None
        if not isinstance(token, str) or not token:
            raise CliError(
                "session_expired",
                "authentication session is missing or expired; run 'hf login'",
            )
        return {"Authorization": f"Bearer {token}"}

    def login(self) -> None:
        if self.config.development:
            return
        assert self._cache_factory is not None
        login_cache = self._cache_factory()
        login_app = self._create_app(login_cache)
        try:
            flow = login_app.initiate_device_flow(scopes=[self.config.scope])
        except _RequestException:
            raise CliError(
                "login_failed",
                "unable to start device login",
            ) from None
        if not isinstance(flow, dict) or not isinstance(flow.get("user_code"), str):
            raise CliError("login_failed", "unable to start device login")
        message = flow.get("message")
        if isinstance(message, str):
            self._notifier(message)
        try:
            deadline = time.monotonic() + self._device_flow_timeout
            result = login_app.acquire_token_by_device_flow(
                flow,
                timeout=self._device_flow_timeout,
                exit_condition=lambda _: time.monotonic() >= deadline,
            )
        except _RequestException:
            raise CliError(
                "login_failed",
                "device login failed",
            ) from None
        token = result.get("access_token") if isinstance(result, dict) else None
        if isinstance(token, str) and token:
            self._persist_cache(cache=login_cache, force=True)
            self._cache = login_cache
            self._app = login_app
            return
        error = result.get("error") if isinstance(result, dict) else None
        if error in {"authorization_declined", "access_denied"}:
            raise CliError("login_denied", "device login was denied")
        if error in {"expired_token", "authorization_pending"}:
            raise CliError("login_timeout", "device login timed out")
        raise CliError("login_failed", "device login failed")

    def logout(self) -> None:
        if self.config.development:
            return
        for account in self._app.get_accounts():
            self._app.remove_account(account)
        remove_saved_session(self.config, keyring_backend=self._keyring)

    def _persist_cache(self, *, cache: Any | None = None, force: bool = False) -> None:
        cache = self._cache if cache is None else cache
        if not force and not getattr(cache, "has_state_changed", False):
            return
        try:
            self._keyring.set_password(
                *self.keyring_location,
                cache.serialize(),
            )
        except _KeyringError:
            raise CliError(
                "keyring_unavailable",
                "unable to save authentication session in the native OS keyring",
            ) from None
