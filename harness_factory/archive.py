from __future__ import annotations

import os
import shutil
import tarfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import BinaryIO

from .contracts import no_symlinks
from .errors import HarnessError

MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_FILE_BYTES = 16 * 1024 * 1024
STREAM_CHUNK_BYTES = 1024 * 1024
MAX_EXTENSION_HEADERS = 100
TAR_BLOCK_BYTES = 512
PAX_HEADER_TYPES = {
    tarfile.XHDTYPE,
    tarfile.XGLTYPE,
    tarfile.SOLARIS_XHDTYPE,
}
GNU_EXTENSION_TYPES = {
    tarfile.GNUTYPE_LONGNAME,
    tarfile.GNUTYPE_LONGLINK,
}


@dataclass
class ArchiveError(HarnessError):
    message: str

    def __str__(self) -> str:
        return self.message


def _fail(message: str) -> None:
    raise ArchiveError(message)


def _member_name(name: str) -> str:
    if not name or "\\" in name or PureWindowsPath(name).drive:
        _fail("archive contains an unsafe path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        _fail("archive contains an unsafe path")
    return path.as_posix()


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(min(STREAM_CHUNK_BYTES, remaining))
        if not chunk:
            _fail("archive is truncated")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _discard_exact(stream: BinaryIO, size: int) -> None:
    remaining = size
    while remaining:
        chunk = stream.read(min(STREAM_CHUNK_BYTES, remaining))
        if not chunk:
            _fail("archive is truncated")
        remaining -= len(chunk)


def _pax_headers(payload: bytes) -> dict[bytes, bytes]:
    headers: dict[bytes, bytes] = {}
    position = 0
    while position < len(payload) and payload[position] != 0:
        space = payload.find(b" ", position)
        if space < 0:
            _fail("archive is not a valid uncompressed tar archive")
        try:
            length = int(payload[position:space])
        except ValueError:
            _fail("archive is not a valid uncompressed tar archive")
        end = position + length
        if length < 5 or end > len(payload) or payload[end - 1] != 0x0A:
            _fail("archive is not a valid uncompressed tar archive")
        keyword, separator, value = payload[space + 1 : end - 1].partition(b"=")
        if not keyword or not separator:
            _fail("archive is not a valid uncompressed tar archive")
        headers[keyword] = value
        position = end
    return headers


def _pax_size(headers: dict[bytes, bytes], fallback: int) -> int:
    value = headers.get(b"size")
    if value is None:
        return fallback
    try:
        size = int(value)
    except ValueError:
        _fail("archive is not a valid uncompressed tar archive")
    if size < 0:
        _fail("archive is not a valid uncompressed tar archive")
    return size


def _preflight_headers(stream: BinaryIO, entry_limit: int) -> None:
    stream.seek(0)
    header_count = 0
    extension_count = 0
    local_pax: dict[bytes, bytes] = {}
    while True:
        header = stream.read(TAR_BLOCK_BYTES)
        if not header:
            return
        if len(header) != TAR_BLOCK_BYTES:
            if header_count:
                _fail("archive is truncated")
            _fail("archive is not a valid uncompressed tar archive")
        if not header.strip(b"\0"):
            return
        header_count += 1
        if header_count > entry_limit:
            _fail("archive has too many entries")
        try:
            member = tarfile.TarInfo.frombuf(
                header,
                encoding="utf-8",
                errors="surrogateescape",
            )
        except (tarfile.TarError, UnicodeError, ValueError):
            _fail("archive is not a valid uncompressed tar archive")

        if member.type in PAX_HEADER_TYPES | GNU_EXTENSION_TYPES:
            extension_count += 1
            if extension_count > MAX_EXTENSION_HEADERS:
                _fail("archive has too many extension headers")
            payload = _read_exact(stream, member.size)
            _discard_exact(stream, -member.size % TAR_BLOCK_BYTES)
            if member.type in PAX_HEADER_TYPES:
                headers = _pax_headers(payload)
                if any(key.startswith(b"GNU.sparse") for key in headers):
                    _fail("archive contains sparse files")
                if member.type != tarfile.XGLTYPE:
                    for key, value in headers.items():
                        local_pax.setdefault(key, value)
            continue

        extension_count = 0
        if member.type == tarfile.GNUTYPE_SPARSE:
            _fail("archive contains sparse files")
        size = _pax_size(local_pax, member.size)
        local_pax.clear()
        if member.isreg() or member.type not in tarfile.SUPPORTED_TYPES:
            _discard_exact(stream, size)
            _discard_exact(stream, -size % TAR_BLOCK_BYTES)


def validate_archive(
    stream: BinaryIO,
    *,
    max_expanded_bytes: int | None = None,
    max_entries: int | None = None,
    max_file_bytes: int | None = None,
) -> None:
    expanded_limit = (
        MAX_EXPANDED_BYTES if max_expanded_bytes is None else max_expanded_bytes
    )
    entry_limit = MAX_ARCHIVE_ENTRIES if max_entries is None else max_entries
    file_limit = MAX_FILE_BYTES if max_file_bytes is None else max_file_bytes
    stream.seek(0)
    seen: set[str] = set()
    expanded_size = 0
    entry_count = 0
    try:
        _preflight_headers(stream, entry_limit)
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            for member in archive:
                entry_count += 1
                if entry_count > entry_limit:
                    _fail("archive has too many entries")
                normalized = _member_name(member.name)
                if normalized in seen:
                    _fail("archive contains duplicate paths")
                seen.add(normalized)
                if member.issym() or member.islnk():
                    _fail("archive contains links")
                if not (member.isfile() or member.isdir()):
                    _fail("archive contains unsupported entries")
                if member.sparse is not None or any(
                    key.startswith("GNU.sparse") for key in member.pax_headers
                ):
                    _fail("archive contains sparse files")
                if member.isdir():
                    continue
                if member.size > file_limit:
                    _fail("archive file exceeds size limit")
                expanded_size += member.size
                if expanded_size > expanded_limit:
                    _fail("archive exceeds expanded size limit")
                extracted = archive.extractfile(member)
                if extracted is None:
                    _fail("archive is malformed")
                with closing(extracted):
                    remaining = member.size
                    while remaining:
                        chunk = extracted.read(min(STREAM_CHUNK_BYTES, remaining))
                        if not chunk:
                            _fail("archive is truncated")
                        remaining -= len(chunk)
    except ArchiveError:
        raise
    except RecursionError:
        _fail("archive has too many extension headers")
    except (OSError, tarfile.TarError, UnicodeError, ValueError):
        _fail("archive is not a valid uncompressed tar archive")


def extract_package(archive: Path, destination: Path) -> None:
    source = Path(archive).absolute()
    target = Path(destination).absolute()
    created = False
    try:
        source = no_symlinks(source)
        target = no_symlinks(target)
        if not source.is_file():
            _fail("archive does not exist")
        if source.stat().st_size > MAX_ARCHIVE_BYTES:
            _fail("archive exceeds archive size limit")
        if target.exists():
            _fail("archive destination already exists")
        with source.open("rb") as stream:
            validate_archive(stream)
        target.mkdir(mode=0o700, parents=False)
        created = True
        with source.open("rb") as stream, tarfile.open(fileobj=stream, mode="r:") as tar:
            for member in tar:
                relative = Path(_member_name(member.name))
                path = no_symlinks(target / relative)
                if member.isdir():
                    path.mkdir(mode=0o700, parents=True, exist_ok=True)
                    path.chmod(0o700)
                    continue
                path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    _fail("archive is malformed")
                with closing(extracted), path.open("xb") as output:
                    remaining = member.size
                    while remaining:
                        chunk = extracted.read(min(STREAM_CHUNK_BYTES, remaining))
                        if not chunk:
                            _fail("archive is truncated")
                        output.write(chunk)
                        remaining -= len(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                path.chmod(0o600)
    except ArchiveError:
        if created:
            shutil.rmtree(target)
        raise
    except RecursionError as exc:
        if created:
            shutil.rmtree(target)
        raise ArchiveError("archive has too many extension headers") from exc
    except (HarnessError, OSError, tarfile.TarError, UnicodeError, ValueError) as exc:
        if created:
            shutil.rmtree(target)
        raise ArchiveError(f"archive extraction failed: {exc}") from exc
