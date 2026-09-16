"""HTTP-backed CLI distribution acceptance built on the lifecycle flow."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import uvicorn

from web.acceptance.postgres_flow import (
    AcceptanceFailure,
    DEFAULT_API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    _expect,
    _expect_status,
    _headers,
    _request,
    get_settings,
    http_transport,
    run_flow,
)
from web.api.config import Settings


@contextmanager
def running_http_app(app):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="error", lifespan="off")
    )
    thread = threading.Thread(
        target=server.run,
        kwargs={"sockets": [listener]},
        daemon=True,
    )
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/api/health", timeout=0.2).status_code == 200:
                break
        except httpx.RequestError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise AcceptanceFailure("HTTP acceptance server did not start")
    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        if thread.is_alive():
            raise AcceptanceFailure("HTTP acceptance server did not stop")


def _console_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["HF_CONFIG_DIR"] = str(root / "config")
    environment["HF_CACHE_DIR"] = str(root / "cache")
    environment.pop("PYTHONPATH", None)
    return environment


def _run_json(
    command: list[str],
    *,
    environment: dict[str, str],
    cwd: Path,
    expected_status: int = 0,
) -> object:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    _expect(
        completed.returncode == expected_status,
        f"{' '.join(command)}: expected exit {expected_status}, got "
        f"{completed.returncode}: {completed.stderr.strip()!r}",
    )
    stream = completed.stdout if expected_status == 0 else completed.stderr
    try:
        return json.loads(stream)
    except json.JSONDecodeError as exc:
        raise AcceptanceFailure(
            f"{' '.join(command)}: expected JSON output, got {stream!r}"
        ) from exc


def _hf(
    executable: str,
    arguments: list[str],
    *,
    environment: dict[str, str],
    cwd: Path,
    expected_status: int = 0,
) -> object:
    return _run_json(
        [executable, *arguments, "--json"],
        environment=environment,
        cwd=cwd,
        expected_status=expected_status,
    )


def _login(
    executable: str,
    *,
    base_url: str,
    organization_id: str,
    subject_id: str,
    roles: tuple[str, ...],
    environment: dict[str, str],
    cwd: Path,
) -> None:
    arguments = [
        "login",
        "--registry",
        base_url,
        "--development",
        "--organization",
        organization_id,
        "--subject",
        subject_id,
    ]
    for role in roles:
        arguments.extend(["--role", role])
    result = _hf(
        executable,
        arguments,
        environment=environment,
        cwd=cwd,
    )
    _expect(result["result"]["authenticated"] is True, "development login failed")  # type: ignore[index]


def run_distribution_flow(
    *,
    settings: Settings,
    workspace: Path,
    hf_executable: str = "hf",
    python_executable: str = sys.executable,
    base_url: str = DEFAULT_API_BASE_URL,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    examples_root: Path | None = None,
    on_build_poll=None,
    require_postgres: bool = True,
) -> dict[str, object]:
    lifecycle = run_flow(
        settings=settings,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        examples_root=examples_root,
        on_build_poll=on_build_poll,
        require_postgres=require_postgres,
    )
    workspace.mkdir(parents=True, exist_ok=False)
    console_cwd = workspace / "outside-checkout"
    console_cwd.mkdir()
    environment = _console_environment(workspace / "developer")
    organization_id = str(lifecycle["organization_id"])
    slug = str(lifecycle["asset_slug"])
    version = str(lifecycle["version"])
    reference = f"{slug}@{version}"

    _login(
        hf_executable,
        base_url=base_url,
        organization_id=organization_id,
        subject_id="distribution-developer",
        roles=("developer",),
        environment=environment,
        cwd=console_cwd,
    )
    search = _hf(
        hf_executable,
        ["search", slug],
        environment=environment,
        cwd=console_cwd,
    )
    _expect(
        any(item.get("slug") == slug for item in search["result"]),  # type: ignore[index, union-attr]
        "published workflow was not returned by CLI search",
    )
    info = _hf(
        hf_executable,
        ["info", reference],
        environment=environment,
        cwd=console_cwd,
    )
    _expect(info["result"]["slug"] == slug, "CLI info returned the wrong workflow")  # type: ignore[index]

    target = workspace / "customer-repository"
    preview_result = _hf(
        hf_executable,
        ["install", reference, "--target", str(target)],
        environment=environment,
        cwd=console_cwd,
    )
    preview = preview_result["result"]  # type: ignore[index]
    _expect(preview["operation"] == "install-preview", "CLI did not preview install")
    _expect(not target.exists(), "install preview mutated the target")

    target.mkdir()
    (target / "customer-owned.txt").write_text("preserved", encoding="utf-8")
    preserved_preview_result = _hf(
        hf_executable,
        ["install", reference, "--target", str(target)],
        environment=environment,
        cwd=console_cwd,
    )
    preserved_preview = preserved_preview_result["result"]  # type: ignore[index]
    _expect(
        preserved_preview["operation"] == "install-preview",
        "CLI did not refresh preview after target creation",
    )
    _expect(
        (target / "customer-owned.txt").read_text(encoding="utf-8") == "preserved",
        "install preview changed an unrelated customer file",
    )
    applied_result = _hf(
        hf_executable,
        [
            "install",
            reference,
            "--target",
            str(target),
            "--approve",
            str(preserved_preview["digest"]),
        ],
        environment=environment,
        cwd=console_cwd,
    )
    applied = applied_result["result"]  # type: ignore[index]
    _expect(applied["operation"] == "install", "CLI did not apply install")
    _expect(
        (target / ".harness" / "manifest.json").is_file(),
        "installed package manifest is missing",
    )
    _expect(
        (target / "customer-owned.txt").read_text(encoding="utf-8") == "preserved",
        "CLI changed an unrelated customer file",
    )

    readiness = _run_json(
        [
            python_executable,
            "-m",
            "harness_factory",
            "delivery-check",
            "--package",
            str(target),
        ],
        environment=environment,
        cwd=console_cwd,
    )
    _expect(readiness["ok"] is True, "installed package delivery check failed")  # type: ignore[index]
    _expect(readiness["ready"] is False, "missing evidence was promoted to ready")  # type: ignore[index]
    _expect(
        readiness["customer_evaluation"]["status"] == "missing",  # type: ignore[index]
        "missing customer evaluation was not reported",
    )

    other_environment = _console_environment(workspace / "other-tenant")
    _login(
        hf_executable,
        base_url=base_url,
        organization_id="acceptance-other",
        subject_id="acceptance-other-subject",
        roles=("developer",),
        environment=other_environment,
        cwd=console_cwd,
    )
    hidden = _hf(
        hf_executable,
        ["info", reference],
        environment=other_environment,
        cwd=console_cwd,
        expected_status=1,
    )
    _expect(hidden["code"] == "not_found", "cross-tenant CLI lookup was not hidden")  # type: ignore[index]

    send = http_transport(base_url)
    revoked = _expect_status(
        _request(
            send,
            "POST",
            f"/api/registry/versions/{lifecycle['version_id']}/revoke",
            headers=_headers(
                organization_id,
                settings.development_subject_id,
                "registry-admin",
            ),
            body={"expected_digest": lifecycle["version_digest"]},
        ),
        200,
        "revoke version",
    )
    _expect(revoked["version"]["status"] == "revoked", "version was not revoked")  # type: ignore[index]
    rejected = _hf(
        hf_executable,
        ["install", reference, "--target", str(workspace / "revoked-target")],
        environment=environment,
        cwd=console_cwd,
        expected_status=1,
    )
    _expect(rejected["code"] == "not_found", "revoked version remained installable")  # type: ignore[index]

    return {
        **lifecycle,
        "operation": "distribution-acceptance",
        "preview_digest": preserved_preview["digest"],
        "installed": True,
        "ready": readiness["ready"],  # type: ignore[index]
        "customer_evaluation": readiness["customer_evaluation"],  # type: ignore[index]
        "cross_tenant": "not_found",
        "revoked_install": "rejected",
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Run HTTP-backed packaged CLI distribution acceptance."
    )
    root.add_argument("--base-url", default=DEFAULT_API_BASE_URL)
    root.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    root.add_argument("--examples-root", default="examples")
    root.add_argument("--workspace", required=True, type=Path)
    root.add_argument("--hf-executable", default="hf")
    root.add_argument("--python-executable", default=sys.executable)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = run_distribution_flow(
            settings=get_settings(),
            workspace=args.workspace,
            hf_executable=args.hf_executable,
            python_executable=args.python_executable,
            base_url=args.base_url,
            timeout_seconds=args.timeout,
            examples_root=Path(args.examples_root),
        )
    except (AcceptanceFailure, OSError, KeyError, TypeError, ValueError) as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "code": "acceptance-failed"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
