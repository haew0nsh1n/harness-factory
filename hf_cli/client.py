from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from harness_factory.archive import MAX_ARCHIVE_BYTES, STREAM_CHUNK_BYTES
from harness_factory.delivery import DeliveryMetadata
from hf_cli.auth import AuthSession
from hf_cli.config import RegistryConfig
from hf_cli.errors import CliError

SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class RegistryClient:
    def __init__(
        self,
        config: RegistryConfig,
        auth: AuthSession,
        *,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self.auth = auth
        self._http = http_client or httpx.Client(
            verify=True,
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
        )

    def whoami(self) -> dict[str, object]:
        payload = self._get("/api/whoami")
        return self._mapping(payload, "actor")

    def search(self, query: str) -> list[dict[str, object]]:
        payload = self._get("/api/registry/assets", params={"query": query})
        items = payload.get("items")
        if not isinstance(items, list) or not all(
            isinstance(item, dict) for item in items
        ):
            raise CliError(
                "invalid_response",
                "registry returned an invalid response",
            )
        return items

    def info(self, slug: str, version: str | None) -> dict[str, object]:
        if not slug:
            raise CliError("invalid_slug", "asset slug is required")
        if version is not None and not SEMVER_RE.fullmatch(version):
            raise CliError(
                "invalid_version",
                "version must use MAJOR.MINOR.PATCH",
            )
        payload = self._get(f"/api/registry/assets/{quote(slug, safe='')}")
        asset = self._mapping(payload, "asset")
        if version is None:
            return asset
        versions = asset.get("versions")
        if not isinstance(versions, list):
            raise CliError("invalid_response", "registry returned an invalid response")
        selected = [
            item
            for item in versions
            if isinstance(item, dict) and item.get("version") == version
        ]
        if not selected:
            raise CliError("not_found", "asset version was not found")
        return {**asset, "versions": selected}

    def delivery(self, version_id: str) -> DeliveryMetadata:
        payload = self._get(
            f"/api/registry/versions/{quote(version_id, safe='')}/delivery"
        )
        raw = self._mapping(payload, "delivery")
        try:
            return DeliveryMetadata.from_mapping(raw)
        except (TypeError, ValueError):
            raise CliError(
                "invalid_response",
                "registry returned invalid delivery metadata",
            ) from None

    def download_artifact(
        self, version_id: str, destination: Path
    ) -> tuple[str, int]:
        path = f"/api/registry/versions/{quote(version_id, safe='')}/artifact"
        written = False
        completed = False
        try:
            with self._http.stream(
                "GET",
                f"{self.config.url}{path}",
                headers=self.auth.headers(),
            ) as response:
                self._check_status(response)
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        raise CliError(
                            "invalid_response",
                            "registry returned an invalid artifact length",
                        ) from None
                    if declared_size < 0:
                        raise CliError(
                            "invalid_response",
                            "registry returned an invalid artifact length",
                        )
                    if declared_size > MAX_ARCHIVE_BYTES:
                        raise CliError(
                            "artifact_too_large",
                            "registry artifact exceeds archive size limit",
                        )
                hasher = hashlib.sha256()
                size = 0
                with Path(destination).open("xb") as output:
                    written = True
                    for chunk in response.iter_bytes(STREAM_CHUNK_BYTES):
                        size += len(chunk)
                        if size > MAX_ARCHIVE_BYTES:
                            raise CliError(
                                "artifact_too_large",
                                "registry artifact exceeds archive size limit",
                            )
                        hasher.update(chunk)
                        output.write(chunk)
                completed = True
                return hasher.hexdigest(), size
        except CliError:
            raise
        except httpx.RequestError:
            raise CliError(
                "network_error",
                "unable to download the registry artifact",
            ) from None
        except OSError:
            raise CliError(
                "download_failed",
                "unable to save the registry artifact",
            ) from None
        finally:
            if written and not completed and Path(destination).exists():
                Path(destination).unlink()

    def _get(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http.get(
                f"{self.config.url}{path}",
                params=params,
                headers=self.auth.headers(),
            )
        except CliError:
            raise
        except httpx.RequestError:
            raise CliError(
                "network_error",
                "unable to connect to the registry",
            ) from None
        self._check_status(response)
        try:
            payload = response.json()
        except ValueError:
            raise CliError(
                "invalid_response",
                "registry returned an invalid response",
            ) from None
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise CliError(
                "invalid_response",
                "registry returned an invalid response",
            )
        return payload

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if 300 <= response.status_code < 400:
            raise CliError(
                "unexpected_redirect",
                "registry returned an unexpected redirect",
            )
        if response.status_code == 401:
            raise CliError("unauthorized", "registry authentication is required")
        if response.status_code == 403:
            raise CliError("forbidden", "registry permission was denied")
        if response.status_code == 404:
            raise CliError("not_found", "registry resource was not found")
        if response.status_code >= 400:
            raise CliError("registry_error", "registry request failed")

    @staticmethod
    def _mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise CliError(
                "invalid_response",
                "registry returned an invalid response",
            )
        return value
