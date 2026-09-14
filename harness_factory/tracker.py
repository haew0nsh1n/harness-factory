from pathlib import Path

from .errors import HarnessError


def _skill_locations(target, home, name):
    return [
        target / ".agents/skills" / name / "SKILL.md",
        target / ".github/skills" / name / "SKILL.md",
        target / ".claude/skills" / name / "SKILL.md",
        home / ".copilot/skills" / name / "SKILL.md",
        home / ".agents/skills" / name / "SKILL.md",
    ]


def _capability_checks(tracker, status):
    return [
        {"capability": capability, "status": status}
        for capability in tracker["capabilities"]
    ]


def _symlink_in_path(path):
    return next(
        (part for part in (path,) + tuple(path.parents) if part.is_symlink()),
        None,
    )


def _skill_name(path):
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, "The selected skill could not be read."
    lines = content.splitlines()
    if not lines or lines[0] != "---":
        return None, "The selected skill has malformed YAML frontmatter."
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None, "The selected skill has malformed YAML frontmatter."
    names = [
        line.split(":", 1)[1].strip()
        for line in lines[1:end]
        if line.startswith("name:")
    ]
    if len(names) != 1:
        return None, "The selected skill has malformed YAML frontmatter."
    return names[0], None


def _skill_guide(tracker, target, home):
    name = tracker["skill"]
    base = {
        "ok": True,
        "operation": "tracker-guide",
        "provider": tracker["provider"],
        "selected": "skill",
        "project": tracker["project"],
        "capabilities": tracker["capabilities"],
        "capability_checks": _capability_checks(tracker, "unverified"),
        "limitations": "Skill availability does not verify provider compatibility, authentication, authorization, or declared capabilities.",
    }
    if _symlink_in_path(target) is not None:
        return dict(
            base,
            status="blocked",
            steps=[
                "Remove the symlink from the project target path and use a regular directory.",
            ],
        )
    rejected = []
    for location in _skill_locations(target, home, name):
        if _symlink_in_path(location) is not None:
            rejected.append(
                "Ignored symlinked skill candidate at " + str(location) + "."
            )
            continue
        if not location.exists():
            continue
        discovered_name, error = _skill_name(location)
        if error is not None:
            rejected.append(error + " Candidate: " + str(location) + ".")
            continue
        if discovered_name != name:
            rejected.append(
                "Ignored candidate whose frontmatter name does not equal "
                + name
                + ": "
                + str(location)
                + "."
            )
            continue
        return dict(
            base,
            status="available",
            skill={"name": name, "location": str(location)},
            steps=[
                "Use the discovered " + name + " skill.",
                "Verify each declared capability against the selected project before workflow execution.",
            ],
        )
    steps = rejected + [
        "Install the selected " + name + " skill in an approved skill location."
    ]
    if tracker["mcp"] is not None:
        steps.append(
            "Regenerate the profile with connection=mcp to use "
            + tracker["mcp"]
            + " instead."
        )
    return dict(base, status="blocked", steps=steps)


def _mcp_guide(tracker):
    name = tracker["mcp"].split(":", 1)[1]
    return {
        "ok": True,
        "operation": "tracker-guide",
        "provider": tracker["provider"],
        "selected": "mcp",
        "status": "manual",
        "project": tracker["project"],
        "capabilities": tracker["capabilities"],
        "capability_checks": _capability_checks(tracker, "manual"),
        "steps": [
            "Open Copilot /mcp and configure the customer-approved "
            + name
            + " server.",
            "Authenticate through the approved native mechanism; do not store credentials in the profile or package.",
            "Verify each declared capability against the selected project before workflow execution.",
        ],
        "limitations": "MCP selection does not verify server configuration, authentication, authorization, or declared capabilities.",
    }


def tracker_guide(profile, target, home=None):
    tracker = profile["issue_tracker"]
    target = Path(target).absolute()
    home = Path.home() if home is None else Path(home).absolute()
    if tracker["connection"] == "local":
        base = {
            "ok": True,
            "operation": "tracker-guide",
            "provider": tracker["provider"],
            "selected": "local",
            "status": "available",
            "project": tracker["project"],
            "capabilities": tracker["capabilities"],
            "capability_checks": _capability_checks(tracker, "unverified"),
            "issue_path": str(target / tracker["path"]),
            "steps": [
                "Use the bundled hf-issues-markdown skill.",
                "Create issue files under " + tracker["path"] + "/<issue-id>.md.",
                "Review Git commit and push separately under repository policy.",
            ],
            "limitations": "Local file availability does not verify Git publication or remote authorization.",
        }
        issue_path = target / tracker["path"]
        if _symlink_in_path(target) is not None or _symlink_in_path(issue_path) is not None:
            return dict(
                base,
                status="blocked",
                steps=[
                    "Remove symlinks from the project target and configured issue path before using local issue files."
                ],
            )
        return base
    if tracker["connection"] == "skill":
        return _skill_guide(tracker, target, home)
    if tracker["connection"] == "mcp":
        return _mcp_guide(tracker)
    raise HarnessError("tracker guide: unsupported connection")
