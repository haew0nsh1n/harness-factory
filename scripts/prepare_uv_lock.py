#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlparse


UV_VERSION = "0.8.3"
ROOT = Path(__file__).resolve().parents[1]


def _safe_index_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("index URL must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("index URL must not include credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("index URL must not include a query string or fragment")
    return value.rstrip("/")


def _locked_versions(path: Path) -> Counter[tuple[str, str]]:
    with path.open("rb") as handle:
        lock = tomllib.load(handle)
    return Counter(
        (package["name"], package["version"])
        for package in lock["package"]
        if "version" in package
    )


def _validate_generated_lock(path: Path, index_url: str) -> None:
    with path.open("rb") as handle:
        lock = tomllib.load(handle)
    registries = {
        package["source"]["registry"].rstrip("/")
        for package in lock["package"]
        if "registry" in package.get("source", {})
    }
    if registries != {index_url}:
        raise RuntimeError(
            "generated lock did not bind every registry package to the selected index"
        )

    for package in lock["package"]:
        urls = []
        if sdist := package.get("sdist"):
            urls.append(sdist["url"])
        urls.extend(wheel["url"] for wheel in package.get("wheels", []))
        for url in urls:
            parsed = urlparse(url)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise RuntimeError("generated lock contains a credentialed artifact URL")


def _uv_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in (
        "PIP_EXTRA_INDEX_URL",
        "PIP_INDEX_URL",
        "UV_DEFAULT_INDEX",
        "UV_EXTRA_INDEX_URL",
        "UV_INDEX",
        "UV_INDEX_URL",
    ):
        environment.pop(name, None)
    return environment


def prepare_lock(
    *,
    index_url: str,
    output: Path,
    base_lock: Path,
    uv_command: str,
    python: str,
) -> None:
    index_url = _safe_index_url(index_url)
    if output.resolve() == base_lock.resolve():
        raise ValueError("output must differ from the base lock")

    version = subprocess.run(
        [uv_command, "--version"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if version.split(maxsplit=2)[:2] != ["uv", UV_VERSION]:
        raise RuntimeError(
            f"feed lock preparation requires uv {UV_VERSION}; found {version}"
        )

    expected_versions = _locked_versions(base_lock)
    with tempfile.TemporaryDirectory(prefix="hf-uv-lock-") as temporary:
        workspace = Path(temporary)
        shutil.copy2(ROOT / "pyproject.toml", workspace / "pyproject.toml")
        shutil.copy2(ROOT / "README.md", workspace / "README.md")
        shutil.copy2(base_lock, workspace / "uv.lock")
        subprocess.run(
            [
                uv_command,
                "lock",
                "--no-config",
                "--default-index",
                index_url,
                "--python",
                python,
                "--no-progress",
            ],
            cwd=workspace,
            env=_uv_environment(),
            check=True,
        )
        generated = workspace / "uv.lock"
        if _locked_versions(generated) != expected_versions:
            raise RuntimeError("selected feed changed locked package versions")
        _validate_generated_lock(generated, index_url)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.with_suffix(f"{output.suffix}.tmp")
        shutil.copy2(generated, temporary_output)
        temporary_output.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a credential-free feed-specific uv lock while preserving "
            "the versions in the repository lock."
        )
    )
    parser.add_argument("--index-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-lock", type=Path, default=ROOT / "uv.lock")
    parser.add_argument("--uv-command", default="uv", help=argparse.SUPPRESS)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    try:
        prepare_lock(
            index_url=args.index_url,
            output=args.output,
            base_lock=args.base_lock,
            uv_command=args.uv_command,
            python=args.python,
        )
    except ValueError as exc:
        parser.error(str(exc))
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
