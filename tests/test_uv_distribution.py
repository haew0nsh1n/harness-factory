from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse

import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_default_lock_uses_public_pypi_artifacts() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    artifact_hosts: set[str] = set()
    registries: set[str] = set()

    for package in lock["package"]:
        source = package.get("source", {})
        if registry := source.get("registry"):
            registries.add(registry)
        if sdist := package.get("sdist"):
            artifact_hosts.add(urlparse(sdist["url"]).hostname or "")
        for wheel in package.get("wheels", []):
            artifact_hosts.add(urlparse(wheel["url"]).hostname or "")

    assert registries == {"https://pypi.org/simple"}
    assert artifact_hosts <= {"files.pythonhosted.org"}


def test_feed_lock_preparation_rejects_credentials(tmp_path: Path) -> None:
    output = tmp_path / "uv.private.lock"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/prepare_uv_lock.py"),
            "--index-url",
            "https://user:secret@packages.example.test/simple",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "must not include credentials" in result.stderr
    assert not output.exists()


def test_feed_lock_preparation_rejects_version_changes(tmp_path: Path) -> None:
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        f"""#!{sys.executable}
import pathlib
import sys

if sys.argv[1:] == ["--version"]:
    print("uv 0.8.3")
else:
    lock = pathlib.Path("uv.lock")
    lock.write_text(lock.read_text().replace(
        'name = "alembic"\\nversion = "1.16.5"',
        'name = "alembic"\\nversion = "9.9.9"',
        1,
    ))
"""
    )
    fake_uv.chmod(0o755)
    output = tmp_path / "uv.private.lock"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/prepare_uv_lock.py"),
            "--index-url",
            "https://packages.example.test/simple",
            "--output",
            str(output),
            "--uv-command",
            str(fake_uv),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "changed locked package versions" in result.stderr
    assert not output.exists()


def test_docker_runtime_uses_explicit_lock_and_no_external_uv_stage() -> None:
    dockerfile = (ROOT / "web/api/Dockerfile").read_text()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert "COPY --from=" not in dockerfile
    assert "python -m pip install --no-cache-dir uv==0.8.3" in dockerfile
    assert "ARG UV_LOCK_FILE=uv.lock" in dockerfile
    assert "COPY ${UV_LOCK_FILE} ./uv.lock" in dockerfile
    assert "UV_INDEX_URL=" not in dockerfile
    assert "python -m venv .venv" in dockerfile
    assert (
        ".venv/bin/python -m pip install --no-cache-dir setuptools==80.9.0"
    ) in dockerfile
    assert "--system-site-packages" not in dockerfile
    assert (
        "uv sync --frozen --no-dev --no-config --no-build-isolation"
    ) in dockerfile
    assert project["build-system"]["requires"] == ["setuptools==80.9.0"]
