from __future__ import annotations

import hashlib
from contextlib import closing
from dataclasses import dataclass
from hmac import compare_digest
from tempfile import SpooledTemporaryFile
from typing import BinaryIO

from web.api.builds.storage import ArtifactStorage, ArtifactStorageError
from harness_factory.archive import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_ENTRIES,
    MAX_EXPANDED_BYTES,
    MAX_FILE_BYTES,
    STREAM_CHUNK_BYTES,
    ArchiveError,
    validate_archive,
)
from web.api.designs.digest import canonical_json_bytes
from web.api.distribution.schemas import DeliveryMetadata
from web.api.registry.models import ASSET_VERSION_STATUS_PUBLISHED, AssetVersion
from web.api.registry.repository import RegistryRepository

SPOOL_MEMORY_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class DeliveryArtifactError(Exception):
    message: str
    code: str


@dataclass
class PreparedDelivery:
    metadata: DeliveryMetadata
    stream: BinaryIO

    def close(self) -> None:
        self.stream.close()


class DistributionService:
    def __init__(
        self,
        repository: RegistryRepository,
        storage: ArtifactStorage,
    ) -> None:
        self._repository = repository
        self._storage = storage

    def prepare(
        self,
        organization_id: str,
        version_id: str,
    ) -> PreparedDelivery | None:
        version = self._repository.get_version(organization_id, version_id)
        if version is None or version.status != ASSET_VERSION_STATUS_PUBLISHED:
            return None
        asset = self._repository.get_asset(organization_id, version.asset_id)
        if asset is None:
            return None

        manifest_digest = hashlib.sha256(
            canonical_json_bytes(version.manifest_json)
        ).hexdigest()
        if not compare_digest(manifest_digest, version.digest):
            raise DeliveryArtifactError(
                "version delivery metadata failed integrity check",
                "artifact_corrupted",
            )
        manifest_artifact = version.manifest_json.get("artifact")
        if (
            not isinstance(manifest_artifact, dict)
            or manifest_artifact.get("key") != version.artifact_key
            or manifest_artifact.get("sha256") != version.artifact_digest
        ):
            raise DeliveryArtifactError(
                "version delivery metadata failed integrity check",
                "artifact_corrupted",
            )

        stream = SpooledTemporaryFile(max_size=SPOOL_MEMORY_BYTES, mode="w+b")
        try:
            artifact_digest, artifact_size = self._copy_and_hash(version, stream)
            self._validate_archive(stream)
            stream.seek(0)
            return PreparedDelivery(
                metadata=DeliveryMetadata(
                    schema_version=1,
                    organization_id=version.organization_id,
                    asset_id=version.asset_id,
                    version_id=version.id,
                    slug=asset.slug,
                    version=version.version,
                    manifest=version.manifest_json,
                    manifest_sha256=manifest_digest,
                    artifact_sha256=artifact_digest,
                    artifact_size=artifact_size,
                ),
                stream=stream,
            )
        except Exception:
            stream.close()
            raise

    def _copy_and_hash(
        self,
        version: AssetVersion,
        destination: BinaryIO,
    ) -> tuple[str, int]:
        hasher = hashlib.sha256()
        size = 0
        try:
            with closing(self._storage.open(version.artifact_key)) as source:
                while chunk := source.read(STREAM_CHUNK_BYTES):
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise DeliveryArtifactError(
                            "stored artifact exceeds archive size limit",
                            "artifact_invalid",
                        )
                    hasher.update(chunk)
                    destination.write(chunk)
        except DeliveryArtifactError:
            raise
        except (ArtifactStorageError, OSError, ValueError):
            raise DeliveryArtifactError(
                "stored artifact is unavailable",
                "artifact_unavailable",
            ) from None

        digest = hasher.hexdigest()
        if not compare_digest(digest, version.artifact_digest):
            raise DeliveryArtifactError(
                "stored artifact failed integrity check",
                "artifact_corrupted",
            )
        return digest, size

    @staticmethod
    def _validate_archive(stream: BinaryIO) -> None:
        try:
            validate_archive(
                stream,
                max_expanded_bytes=MAX_EXPANDED_BYTES,
                max_entries=MAX_ARCHIVE_ENTRIES,
                max_file_bytes=MAX_FILE_BYTES,
            )
        except ArchiveError as exc:
            raise DeliveryArtifactError(
                "stored artifact " + exc.message.removeprefix("archive "),
                "artifact_invalid",
            ) from None
