import shutil
import subprocess
from pathlib import Path

from .contracts import load_json
from .errors import HarnessError
from .package import check_package
from .tracker import tracker_guide

KNOWN_CLI = {"gh", "git", "python3"}


def preflight(package, allow_read_probes=False, home=None):
    check_package(package)
    profile = load_json(Path(package) / ".harness/customer.json")
    tracker = tracker_guide(profile, Path(package), home=home)
    items = []
    for system in profile["systems"]:
        token = system["tool"]
        item = {"system": system["id"], "tool": token,
                "executable": {"status": "unverified"},
                "authentication": {"status": "unverified", "scope": "identity-only"},
                "capabilities": [{"capability": capability, "status": "unverified"}
                                 for capability in system["capabilities"]]}
        if token.startswith("mcp:"):
            item.update(status="manual", detail="MCP readiness requires a customer-side manual check.")
            item["executable"]["status"] = "manual"
            item["authentication"]["status"] = "manual"
            for capability in item["capabilities"]:
                capability["status"] = "manual"
        elif token.startswith("skill:"):
            selected = (
                profile["issue_tracker"]["connection"] == "skill"
                and token == "skill:" + profile["issue_tracker"]["skill"]
            )
            available = selected and tracker["status"] == "available"
            item.update(
                status="available" if available else "unverified",
                detail=(
                    "Selected tracker skill is installed; provider compatibility, authorization, and capabilities remain unverified."
                    if available
                    else "Skill availability was not confirmed for this system."
                ),
            )
            item["executable"]["status"] = "available" if available else "unverified"
        elif token not in KNOWN_CLI:
            item.update(status="unverified", detail="Unsupported CLI; no executable or authentication probe performed.")
        else:
            try:
                executable = shutil.which(token)
            except OSError as exc:
                raise HarnessError("preflight executable lookup: " + str(exc)) from exc
            item.update(status="available" if executable else "missing",
                        detail="Availability only; authorization and workflow readiness are unverified.")
            item["executable"]["status"] = "available" if executable else "missing"
            if allow_read_probes and executable and token == "gh":
                results = []
                for args in ([executable, "auth", "status"], [executable, "api", "user"]):
                    try:
                        result = subprocess.run(args, shell=False, timeout=10,
                                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL)
                        results.append("passed" if result.returncode == 0 else "failed")
                    except subprocess.TimeoutExpired:
                        results.append("timeout")
                    except OSError:
                        results.append("unavailable")
                item.update(status="verified-read" if all(r == "passed" for r in results) else "unverified",
                            detail="Identity probes do not verify repository read/write access or declared capabilities.",
                            probes=[{"command": "gh auth status", "status": results[0]},
                                    {"command": "gh api user", "status": results[1]}])
                if all(r == "passed" for r in results):
                    item["authentication"]["status"] = "verified-identity"
        items.append(item)
    return {"ok": True, "operation": "preflight", "read_probes": bool(allow_read_probes),
            "ready": False, "issue_tracker": tracker, "items": items,
            "limitations": "Readiness requires human review of capabilities, permissions, manual handoffs and actual completion checks."}
