from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

import pytest


def tar_bytes(members: list[tarfile.TarInfo | tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for item in members:
            if isinstance(item, tuple):
                name, data = item
                member = tarfile.TarInfo(name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            else:
                archive.addfile(item)
    return buffer.getvalue()


def pax_chain_bytes(count: int, name: str = "file.txt") -> bytes:
    members: list[tarfile.TarInfo | tuple[str, bytes]] = []
    for index in range(count):
        member = tarfile.TarInfo(f"pax-{index}")
        member.type = tarfile.XHDTYPE
        members.append(member)
    members.append((name, b"x"))
    return tar_bytes(members)


def raw_header(name: str, size: int, typeflag: bytes = tarfile.REGTYPE) -> bytes:
    header = bytearray(512)
    header[: len(name)] = name.encode("ascii")
    header[100:108] = b"0000600\0"
    header[108:116] = b"0000000\0"
    header[116:124] = b"0000000\0"
    header[124:136] = f"{size:011o}\0".encode("ascii")
    header[136:148] = b"00000000000\0"
    header[148:156] = b"        "
    header[156:157] = typeflag
    header[257:263] = b"ustar\0"
    header[263:265] = b"00"
    checksum = sum(header)
    header[148:156] = f"{checksum:06o}\0 ".encode("ascii")
    return bytes(header)


def pax_record(key: str, value: str) -> bytes:
    body = f" {key}={value}\n".encode("utf-8")
    length = len(body) + 1
    while True:
        record = str(length).encode("ascii") + body
        if len(record) == length:
            return record
        length = len(record)


def pad_block(payload: bytes) -> bytes:
    return payload + (b"\0" * (-len(payload) % 512))


def special_member(kind: str) -> tarfile.TarInfo:
    names = {
        "absolute": "/outside",
        "parent": "../outside",
        "windows": r"..\outside",
        "windows-drive": "C:/outside",
        "symlink": "link",
        "hardlink": "link",
        "fifo": "pipe",
        "device": "device",
        "sparse": "sparse.bin",
    }
    member = tarfile.TarInfo(names[kind])
    if kind == "symlink":
        member.type = tarfile.SYMTYPE
        member.linkname = "target"
    elif kind == "hardlink":
        member.type = tarfile.LNKTYPE
        member.linkname = "target"
    elif kind == "fifo":
        member.type = tarfile.FIFOTYPE
    elif kind == "device":
        member.type = tarfile.CHRTYPE
    elif kind == "sparse":
        member.size = 1
        member.pax_headers = {"GNU.sparse.map": "0,1"}
    return member


def test_archive_limits_match_distribution_contract() -> None:
    from hf_cli import archive

    assert archive.MAX_ARCHIVE_BYTES == 100 * 1024 * 1024
    assert archive.MAX_EXPANDED_BYTES == 256 * 1024 * 1024
    assert archive.MAX_ARCHIVE_ENTRIES == 10_000
    assert archive.MAX_FILE_BYTES == 16 * 1024 * 1024


@pytest.mark.parametrize(
    "members",
    [
        [special_member("absolute")],
        [special_member("parent")],
        [special_member("windows")],
        [special_member("windows-drive")],
        [("same.txt", b"a"), ("same.txt", b"b")],
        [special_member("symlink")],
        [special_member("hardlink")],
        [special_member("fifo")],
        [special_member("device")],
        [special_member("sparse")],
    ],
)
def test_extract_rejects_unsafe_duplicate_link_and_special_members(
    tmp_path: Path,
    members: list[tarfile.TarInfo | tuple[str, bytes]],
) -> None:
    from hf_cli.archive import ArchiveError, extract_package

    archive = tmp_path / "package.tar"
    archive.write_bytes(tar_bytes(members))
    destination = tmp_path / "package"

    with pytest.raises(ArchiveError):
        extract_package(archive, destination)

    assert not destination.exists()
    assert not (tmp_path / "outside").exists()


def test_extract_accepts_exact_file_expanded_and_entry_boundaries(
    tmp_path: Path, monkeypatch
) -> None:
    from harness_factory import archive as archive_module

    monkeypatch.setattr(archive_module, "MAX_FILE_BYTES", 3)
    monkeypatch.setattr(archive_module, "MAX_EXPANDED_BYTES", 4)
    monkeypatch.setattr(archive_module, "MAX_ARCHIVE_ENTRIES", 2)
    source = tmp_path / "package.tar"
    source.write_bytes(tar_bytes([("a.txt", b"123"), ("b.txt", b"4")]))
    destination = tmp_path / "package"

    archive_module.extract_package(source, destination)

    assert (destination / "a.txt").read_bytes() == b"123"
    assert (destination / "b.txt").read_bytes() == b"4"
    assert destination.stat().st_mode & 0o777 == 0o700
    assert (destination / "a.txt").stat().st_mode & 0o777 == 0o600


def test_extract_rejects_extension_chain_as_archive_error_without_output(
    tmp_path: Path,
) -> None:
    from hf_cli.archive import ArchiveError, extract_package

    source = tmp_path / "pax-chain.tar"
    source.write_bytes(pax_chain_bytes(1_100, "../outside"))
    destination = tmp_path / "package"

    with pytest.raises(ArchiveError, match="too many extension headers"):
        extract_package(source, destination)

    assert not destination.exists()
    assert not (tmp_path / "outside").exists()


def test_validate_counts_raw_extension_headers_before_tarfile_iteration() -> None:
    from hf_cli.archive import ArchiveError, validate_archive

    with pytest.raises(ArchiveError, match="too many entries"):
        validate_archive(io.BytesIO(pax_chain_bytes(3)), max_entries=1)


def test_extract_accepts_normal_pax_size_override(tmp_path: Path) -> None:
    from hf_cli.archive import extract_package

    pax = pax_record("size", "3")
    payload = (
        raw_header("pax-size", len(pax), tarfile.XHDTYPE)
        + pad_block(pax)
        + raw_header("file.txt", 0)
        + pad_block(b"abc")
        + (b"\0" * 1024)
    )
    source = tmp_path / "pax.tar"
    source.write_bytes(payload)
    destination = tmp_path / "package"

    extract_package(source, destination)

    assert (destination / "file.txt").read_bytes() == b"abc"


@pytest.mark.parametrize(
    ("limit", "members", "message"),
    [
        ("file", [("large.txt", b"1234")], "file exceeds size limit"),
        ("expanded", [("a.txt", b"12"), ("b.txt", b"34")], "expanded size limit"),
        ("entries", [("a.txt", b"a"), ("b.txt", b"b")], "too many entries"),
    ],
)
def test_extract_rejects_one_past_each_boundary(
    tmp_path: Path,
    monkeypatch,
    limit: str,
    members: list[tuple[str, bytes]],
    message: str,
) -> None:
    from harness_factory import archive as archive_module

    monkeypatch.setattr(
        archive_module, "MAX_FILE_BYTES", 3 if limit == "file" else 10
    )
    monkeypatch.setattr(
        archive_module, "MAX_EXPANDED_BYTES", 3 if limit == "expanded" else 10
    )
    monkeypatch.setattr(
        archive_module, "MAX_ARCHIVE_ENTRIES", 1 if limit == "entries" else 10
    )
    source = tmp_path / f"{limit}.tar"
    source.write_bytes(tar_bytes(members))

    with pytest.raises(archive_module.ArchiveError, match=message):
        archive_module.extract_package(source, tmp_path / f"{limit}-out")


@pytest.mark.parametrize("payload", [b"", b"not a tar"])
def test_extract_rejects_empty_and_corrupt_archives(
    tmp_path: Path, payload: bytes
) -> None:
    from hf_cli.archive import ArchiveError, extract_package

    source = tmp_path / "bad.tar"
    source.write_bytes(payload)

    with pytest.raises(ArchiveError, match="valid uncompressed tar"):
        extract_package(source, tmp_path / "out")


def test_extract_rejects_compressed_and_deceptive_truncated_size(
    tmp_path: Path,
) -> None:
    from hf_cli.archive import ArchiveError, extract_package

    compressed = io.BytesIO()
    with tarfile.open(fileobj=compressed, mode="w:gz") as archive:
        member = tarfile.TarInfo("file.txt")
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    compressed_path = tmp_path / "compressed.tar.gz"
    compressed_path.write_bytes(compressed.getvalue())
    with pytest.raises(ArchiveError, match="uncompressed tar"):
        extract_package(compressed_path, tmp_path / "compressed")

    valid = bytearray(tar_bytes([("file.txt", b"x")]))
    valid[124:136] = b"00000000010\x00"
    checksum = sum(valid[:148]) + (32 * 8) + sum(valid[156:512])
    valid[148:156] = f"{checksum:06o}\0 ".encode()
    truncated_path = tmp_path / "truncated.tar"
    truncated_path.write_bytes(bytes(valid[:513]))
    with pytest.raises(ArchiveError, match="truncated|valid uncompressed tar"):
        extract_package(truncated_path, tmp_path / "truncated")


def test_extract_refuses_existing_destination_and_symlink_ancestor(
    tmp_path: Path,
) -> None:
    from hf_cli.archive import ArchiveError, extract_package

    source = tmp_path / "package.tar"
    source.write_bytes(tar_bytes([("file.txt", b"x")]))
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "keep.txt").write_text("keep")
    with pytest.raises(ArchiveError, match="destination"):
        extract_package(source, existing)
    assert (existing / "keep.txt").read_text() == "keep"

    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ArchiveError, match="symlink"):
        extract_package(source, link / "package")
    assert not (real / "package").exists()
