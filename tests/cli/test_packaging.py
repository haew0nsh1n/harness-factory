from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_wheel_installs_hf_outside_checkout_without_portal_content(
    packaged_cli,
) -> None:
    names = packaged_cli.wheel_names
    assert any(name == "hf_cli/main.py" for name in names)
    assert not any("node_modules" in name for name in names)
    assert not any(name.startswith("web/portal/") for name in names)

    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    helped = subprocess.run(
        [str(packaged_cli.hf), "--help"],
        cwd=packaged_cli.outside,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert helped.returncode == 0, helped.stderr
    assert "authenticate to a registry" in helped.stdout
    assert str(ROOT) not in helped.stdout
    assert Path(packaged_cli.origins["hf_cli"]).is_relative_to(packaged_cli.root)
    assert Path(packaged_cli.origins["harness_factory"]).is_relative_to(
        packaged_cli.root
    )
    for dependency in ("httpx", "keyring", "msal"):
        assert Path(packaged_cli.origins[dependency]).is_relative_to(
            packaged_cli.root
        )
