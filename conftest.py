from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import venv
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.prepare_uv_lock import _safe_index_url as validate_feed_url

ROOT = Path(__file__).resolve().parent
PUBLIC_INDEX = "https://pypi.org/simple"


def _safe_index_url(value: str) -> str:
    try:
        return validate_feed_url(value)
    except ValueError:
        raise pytest.UsageError(
            "HF_ACCEPTANCE_INDEX_URL must be an absolute credential-free HTTPS URL"
        ) from None


def _configured_index_url() -> str:
    explicit = os.environ.get("HF_ACCEPTANCE_INDEX_URL")
    if explicit:
        return _safe_index_url(explicit)
    python = shutil.which("python3")
    if python is not None:
        configured = subprocess.run(
            [python, "-m", "pip", "config", "get", "global.index-url"],
            text=True,
            capture_output=True,
            check=False,
        )
        if configured.returncode == 0 and configured.stdout.strip():
            return _safe_index_url(configured.stdout.strip())
    return PUBLIC_INDEX


def _package_source(source: Path) -> None:
    source.mkdir()
    for name in ("harness_factory", "hf_cli"):
        shutil.copytree(ROOT / name, source / name)
    (source / "web").mkdir()
    shutil.copy2(ROOT / "web" / "__init__.py", source / "web" / "__init__.py")
    for name in ("acceptance", "api"):
        shutil.copytree(ROOT / "web" / name, source / "web" / name)
    portal = source / "web" / "portal"
    (portal / "node_modules").mkdir(parents=True)
    (portal / "sentinel.txt").write_text("must not ship\n", encoding="utf-8")
    (portal / "node_modules" / "sentinel.js").write_text(
        "must not ship\n",
        encoding="utf-8",
    )
    shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
    shutil.copy2(ROOT / "README.md", source / "README.md")
    shutil.copy2(ROOT / "uv.lock", source / "uv.lock")


def _feed_arguments() -> list[str]:
    wheelhouse = os.environ.get("HF_ACCEPTANCE_WHEELHOUSE")
    if wheelhouse:
        path = Path(wheelhouse).expanduser().resolve()
        if not path.is_dir():
            raise pytest.UsageError(
                "HF_ACCEPTANCE_WHEELHOUSE must name an existing directory"
            )
        return ["--no-index", "--find-links", str(path)]
    return ["--default-index", _configured_index_url()]


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.fixture(scope="session")
def packaged_cli(tmp_path_factory):
    root = tmp_path_factory.mktemp("packaged-cli")
    source = root / "source"
    _package_source(source)
    distribution = root / "dist"
    feed_arguments = _feed_arguments()
    built = _run(
        [
            "uv",
            "--no-config",
            "build",
            "--wheel",
            *feed_arguments,
            "--out-dir",
            str(distribution),
        ],
        cwd=source,
    )
    assert built.returncode == 0, built.stderr
    wheels = list(distribution.glob("harness_factory-*.whl"))
    assert len(wheels) == 1
    wheel = wheels[0]

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = tuple(archive.namelist())

    requirements = root / "locked-requirements.txt"
    exported = _run(
        [
            "uv",
            "--no-config",
            "export",
            "--frozen",
            "--extra",
            "cli",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(requirements),
        ],
        cwd=source,
    )
    assert exported.returncode == 0, exported.stderr

    environment_root = root / "installed"
    venv.EnvBuilder(with_pip=True).create(environment_root)
    python = environment_root / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    hf = environment_root / ("Scripts/hf.exe" if os.name == "nt" else "bin/hf")
    installed = _run(
        [
            "uv",
            "--no-config",
            "pip",
            "install",
            "--python",
            str(python),
            *feed_arguments,
            "--requirement",
            str(requirements),
            f"{wheel}[cli]",
        ],
        cwd=root,
    )
    assert installed.returncode == 0, installed.stderr

    outside = root / "outside-checkout"
    outside.mkdir()
    origins_result = _run(
        [
            str(python),
            "-I",
            "-c",
            (
                "import json, hf_cli, harness_factory, httpx, keyring, msal; "
                "print(json.dumps({'hf_cli': hf_cli.__file__, "
                "'harness_factory': harness_factory.__file__, "
                "'httpx': httpx.__file__, 'keyring': keyring.__file__, "
                "'msal': msal.__file__}))"
            ),
        ],
        cwd=outside,
    )
    assert origins_result.returncode == 0, origins_result.stderr
    origins = json.loads(origins_result.stdout)
    installed_root = environment_root.resolve()
    checkout_root = ROOT.resolve()
    for origin in origins.values():
        resolved = Path(origin).resolve()
        assert resolved.is_relative_to(installed_root)
        assert not resolved.is_relative_to(checkout_root)

    return SimpleNamespace(
        hf=hf,
        python=python,
        root=environment_root,
        outside=outside,
        origins=origins,
        wheel=wheel,
        wheel_names=wheel_names,
    )
