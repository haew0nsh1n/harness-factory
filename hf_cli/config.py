from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import overload
from urllib.parse import urlsplit, urlunsplit

from hf_cli.errors import CliError


@dataclass(frozen=True)
class RegistryConfig:
    url: str
    tenant_id: str
    client_id: str
    scope: str
    development: bool = False


@dataclass(frozen=True)
class DevelopmentIdentity:
    organization: str
    subject: str
    roles: tuple[str, ...]


def default_config_path() -> Path:
    root = os.environ.get("HF_CONFIG_DIR") or os.environ.get("XDG_CONFIG_HOME")
    base = Path(root).expanduser() if root else Path.home() / ".config"
    return base / "harness-factory" / "config.json"


def validate_registry_url(url: str, *, development: bool) -> str:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise CliError("invalid_registry_url", "registry URL is invalid") from None
    if parsed.username is not None or parsed.password is not None:
        raise CliError(
            "invalid_registry_url",
            "registry URL must not contain credentials",
        )
    if (
        not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise CliError(
            "invalid_registry_url",
            "registry URL must be a strict origin without a path, query, or fragment",
        )
    if development:
        try:
            address = ipaddress.ip_address(parsed.hostname)
        except ValueError:
            raise CliError(
                "invalid_registry_url",
                "development registry must use a literal loopback address",
            ) from None
        if not address.is_loopback or parsed.scheme not in {"http", "https"}:
            raise CliError(
                "invalid_registry_url",
                "development registry must use a literal loopback HTTP(S) origin",
            )
    elif parsed.scheme != "https":
        raise CliError(
            "invalid_registry_url",
            "production registry URL must use HTTPS",
        )
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def _validate_config(config: RegistryConfig) -> RegistryConfig:
    values = (config.tenant_id, config.client_id, config.scope)
    if any(not value or not value.strip() for value in values):
        raise CliError(
            "invalid_config",
            "registry tenant, client ID, and scope are required",
        )
    return RegistryConfig(
        url=validate_registry_url(config.url, development=config.development),
        tenant_id=config.tenant_id.strip(),
        client_id=config.client_id.strip(),
        scope=config.scope.strip(),
        development=config.development,
    )


def save_config(
    config: RegistryConfig,
    *,
    development_identity: DevelopmentIdentity | None = None,
    path: Path | None = None,
) -> None:
    config = _validate_config(config)
    if config.development != (development_identity is not None):
        raise CliError(
            "invalid_config",
            "development identity must be provided only for development mode",
        )
    destination = path or default_config_path()
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        destination.parent.chmod(0o700)
        payload: dict[str, object] = asdict(config)
        if development_identity is not None:
            if (
                not development_identity.organization
                or not development_identity.subject
                or not development_identity.roles
            ):
                raise CliError(
                    "invalid_config",
                    "development organization, subject, and roles are required",
                )
            payload["development_identity"] = {
                "organization": development_identity.organization,
                "subject": development_identity.subject,
                "roles": list(development_identity.roles),
            }
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(destination)
        destination.chmod(0o600)
    except CliError:
        raise
    except OSError:
        raise CliError(
            "config_write_failed",
            "unable to save registry configuration",
        ) from None


@overload
def load_config(
    *, path: Path | None = None, include_development_identity: bool = False
) -> RegistryConfig: ...


@overload
def load_config(
    *, path: Path | None = None, include_development_identity: bool
) -> tuple[RegistryConfig, DevelopmentIdentity | None]: ...


def load_config(
    *,
    path: Path | None = None,
    include_development_identity: bool = False,
) -> RegistryConfig | tuple[RegistryConfig, DevelopmentIdentity | None]:
    source = path or default_config_path()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError
        allowed = {
            "url",
            "tenant_id",
            "client_id",
            "scope",
            "development",
            "development_identity",
        }
        if set(raw) - allowed:
            raise ValueError
        config = _validate_config(
            RegistryConfig(
                url=_required_string(raw, "url"),
                tenant_id=_required_string(raw, "tenant_id"),
                client_id=_required_string(raw, "client_id"),
                scope=_required_string(raw, "scope"),
                development=raw.get("development", False) is True,
            )
        )
        identity = _load_development_identity(raw, config)
    except FileNotFoundError:
        raise CliError(
            "not_configured",
            "registry is not configured; run 'hf login' first",
        ) from None
    except CliError:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise CliError(
            "invalid_config",
            "registry configuration is invalid",
        ) from None
    if include_development_identity:
        return config, identity
    return config


def _required_string(raw: dict[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError
    return value


def _load_development_identity(
    raw: dict[str, object], config: RegistryConfig
) -> DevelopmentIdentity | None:
    value = raw.get("development_identity")
    if not config.development:
        if value is not None:
            raise ValueError
        return None
    if not isinstance(value, dict):
        raise ValueError
    roles = value.get("roles")
    organization = value.get("organization")
    subject = value.get("subject")
    if (
        not isinstance(organization, str)
        or not organization
        or not isinstance(subject, str)
        or not subject
        or not isinstance(roles, list)
        or not roles
        or not all(isinstance(role, str) and role for role in roles)
    ):
        raise ValueError
    return DevelopmentIdentity(organization, subject, tuple(roles))
