from __future__ import annotations

import errno
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from harness_factory.contracts import no_symlinks
from harness_factory.errors import ValidationError

# Mounts such as Azure Files (SMB) reject hardlinks; fall back to a rename create.
_LINK_UNSUPPORTED_ERRNOS = frozenset(
    {errno.EPERM, errno.ENOSYS, errno.EOPNOTSUPP, errno.EXDEV}
)


@dataclass(frozen=True)
class StoredArtifact:
    key: str
    sha256: str
    size: int


class ArtifactStorage(Protocol):
    def put_once(self, key: str, source: Path) -> StoredArtifact: ...

    def open(self, key: str) -> BinaryIO: ...


class ArtifactStorageError(ValueError):
    pass


class ArtifactConflict(ArtifactStorageError):
    pass


def _normalize_path(path: Path) -> Path:
    try:
        return no_symlinks(path)
    except ValidationError as exc:
        raise ArtifactStorageError(str(exc)) from exc


def _normalize_key(key: str) -> Path:
    if not isinstance(key, str) or not key:
        raise ArtifactStorageError("artifact key must be a nonempty string")
    relative = Path(key)
    if relative.is_absolute() or "\\" in key:
        raise ArtifactStorageError("artifact key must be a safe relative path")
    parts = relative.parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ArtifactStorageError("artifact key must be a safe relative path")
    return relative


def _digest_file(path: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
            size += len(chunk)
    return hasher.hexdigest(), size


class FileArtifactStorage:
    def __init__(self, root: Path) -> None:
        self._root = _normalize_path(Path(root))
        self._root.mkdir(parents=True, exist_ok=True)

    def put_once(self, key: str, source: Path) -> StoredArtifact:
        relative = _normalize_key(key)
        normalized_source = _normalize_path(Path(source))
        if not normalized_source.is_file():
            raise ArtifactStorageError("artifact source must be a regular file")

        destination = _normalize_path(self._root / relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=".artifact-",
                delete=False,
            ) as scratch:
                temporary_path = scratch.name
                with normalized_source.open("rb") as stream:
                    shutil.copyfileobj(stream, scratch)
                scratch.flush()
                os.fsync(scratch.fileno())

            scratch_path = _normalize_path(Path(temporary_path))
            source_digest, source_size = _digest_file(scratch_path)

            def _dedup_or_conflict() -> StoredArtifact:
                existing_digest, existing_size = _digest_file(destination)
                if (
                    existing_digest == source_digest
                    and existing_size == source_size
                ):
                    return StoredArtifact(
                        key=relative.as_posix(),
                        sha256=existing_digest,
                        size=existing_size,
                    )
                raise ArtifactConflict("artifact already exists with different bytes")

            try:
                os.link(scratch_path, destination)
            except FileExistsError:
                return _dedup_or_conflict()
            except OSError as link_exc:
                if link_exc.errno not in _LINK_UNSUPPORTED_ERRNOS:
                    raise
                if destination.exists():
                    return _dedup_or_conflict()
                os.replace(scratch_path, destination)
                temporary_path = None

            return StoredArtifact(
                key=relative.as_posix(),
                sha256=source_digest,
                size=source_size,
            )
        except OSError as exc:
            raise ArtifactStorageError(str(exc)) from exc
        finally:
            if temporary_path is not None:
                try:
                    Path(temporary_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def open(self, key: str) -> BinaryIO:
        relative = _normalize_key(key)
        path = _normalize_path(self._root / relative)
        if not path.is_file():
            raise ArtifactStorageError("stored artifact must be a regular file")
        try:
            return path.open("rb")
        except OSError as exc:
            raise ArtifactStorageError(str(exc)) from exc
