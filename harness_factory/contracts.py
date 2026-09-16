import json
import re
import hashlib
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from .errors import ValidationError

IDENTIFIER = re.compile(r"[a-z][a-z0-9-]*\Z")
TOOL = re.compile(r"[a-z][a-z0-9-]*\.[a-z][a-z0-9-]*\Z")
SYSTEM_TOKEN = re.compile(r"(?:(?:mcp|skill):)?[a-z][a-z0-9-]*\Z")
EFFECTS = {"read", "local", "external-write", "manual"}
TRACKER_PROVIDERS = {"markdown", "github", "jira"}
TRACKER_CONNECTIONS = {"local", "skill", "mcp"}
TRACKER_CAPABILITIES = {
    "issue-read", "issue-create", "issue-update", "issue-transition", "issue-comment",
}
TRACKER_WRITE_CAPABILITIES = {
    "issue-create", "issue-update", "issue-transition", "issue-comment",
}
PROJECT_PART = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?"


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def text(value, field):
    require(isinstance(value, str) and bool(value.strip()), field + ": expected nonempty string")
    return value


def identifier(value, field):
    text(value, field)
    require(IDENTIFIER.fullmatch(value), field + ": expected lowercase hyphen identifier")
    return value


def optional_text(value, field):
    if value is not None:
        text(value, field)
    return value


def tracker_project(value, provider):
    text(value, "profile.issue_tracker.project")
    if provider == "github":
        valid = re.fullmatch(PROJECT_PART + "/" + PROJECT_PART, value)
    elif provider == "jira":
        valid = re.fullmatch(r"[A-Z][A-Z0-9_-]*", value)
    else:
        valid = re.fullmatch(PROJECT_PART, value)
    require(valid is not None, "profile.issue_tracker.project: invalid provider project identifier")
    return value


def shape(value, fields, field, optional=""):
    require(isinstance(value, dict), field + ": expected object")
    required = set(fields.split())
    expected = required | set(optional.split())
    require(not (set(value) - expected), field + ": unknown fields " + ", ".join(sorted(set(value) - expected)))
    require(not (required - set(value)), field + ": missing fields " + ", ".join(sorted(required - set(value))))


def strings(value, field, nonempty=False, ids=False):
    require(isinstance(value, list), field + ": expected array")
    require(not nonempty or bool(value), field + ": must not be empty")
    for i, item in enumerate(value):
        (identifier if ids else text)(item, "{}[{}]".format(field, i))
    require(len(set(value)) == len(value), field + ": duplicate value")
    return value


def objects(value, field, nonempty=False):
    require(isinstance(value, list), field + ": expected array")
    require(not nonempty or bool(value), field + ": must not be empty")
    require(all(isinstance(v, dict) for v in value), field + ": expected objects")
    return value


def no_symlinks(path):
    path = Path(path).absolute()
    for part in [path] + list(path.parents):
        require(not part.is_symlink(), str(part) + ": symlink is not allowed")
    return path


def relative_path(root, value, field, directory=False, must_exist=True):
    text(value, field)
    rel = Path(value)
    require(not rel.is_absolute() and "\\" not in value and
            all(p not in ("", ".", "..") for p in value.split("/")),
            field + ": unsafe relative path")
    root = no_symlinks(root)
    path = no_symlinks(root / rel)
    require(root.resolve() in path.resolve().parents, field + ": path escapes root")
    if must_exist:
        require(path.is_dir() if directory else path.is_file(), field + ": missing " + value)
    return path


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON: duplicate key " + key)
        result[key] = value
    return result


def load_json(path):
    try:
        with no_symlinks(path).open(encoding="utf-8") as stream:
            result = json.load(stream, object_pairs_hook=_pairs,
                               parse_constant=lambda value: require(False, "JSON: invalid constant " + value))
        require(isinstance(result, dict), str(path) + ": JSON root must be an object")
        return result
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError("{}: {}".format(path, exc)) from exc


def _version(value, field):
    require(type(value) is int and value == 1, field + ": schema_version must be 1")


def _unique(items, field, key="id"):
    seen = {}
    for item in items:
        value = identifier(item.get(key), field + "." + key)
        require(value not in seen, field + ": duplicate " + value)
        seen[value] = item
    return seen


def _validate_evidence(root, skill):
    field = "catalog.skills.compatibility.evidence"
    report = load_json(relative_path(root, skill["compatibility"]["evidence"], field))
    _version(report.get("schema_version"), field)
    require(report.get("runtime") == "copilot-cli", field + ": expected copilot-cli runtime")
    skills = report.get("skills")
    require(isinstance(skills, dict) and bool(skills), field + ".skills: expected nonempty hash map")
    for name, digest in skills.items():
        identifier(name, field + ".skills")
        require(isinstance(digest, str) and re.fullmatch("[a-f0-9]{64}", digest),
                field + ".skills: invalid SHA-256 hash")
    entry = relative_path(root, skill["path"], "catalog.skills.path", directory=True) / "SKILL.md"
    actual = hashlib.sha256(no_symlinks(entry).read_bytes()).hexdigest()
    require(skills.get(skill["id"]) == actual, field + ": skill hash mismatch; re-evaluate changed SKILL.md")
    for case in objects(report.get("cases"), field + ".cases", nonempty=True):
        require(case.get("pass") is True, field + ".cases: all observed cases must have pass=true")


def _markdown_destination(value):
    value = value.lstrip()
    if value.startswith("<"):
        end = value.find(">")
        require(end != -1, "skill.reference: unterminated angle-bracket destination")
        return value[1:end]
    result = []
    depth = 0
    index = 0
    while index < len(value):
        char = value[index]
        if char == "\\" and index + 1 < len(value):
            result.append(value[index + 1])
            index += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        elif char.isspace() and depth == 0:
            break
        result.append(char)
        index += 1
    return "".join(result)


def _markdown_without_code(content):
    lines = []
    fence = None
    for line in content.splitlines(keepends=True):
        marker = re.match(r" {0,3}(`{3,}|~{3,})", line)
        if fence is not None:
            if marker and marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = None
            continue
        if marker:
            fence = marker.group(1)
        else:
            lines.append(line)
    return re.sub(r"(`+).*?\1", "", "".join(lines), flags=re.DOTALL)


def _validate_skill_references(directory):
    directory = no_symlinks(directory)

    def walk_error(error):
        raise error

    def check_reference(markdown, target):
        if not target or target.startswith("#"):
            return
        field = "skill.reference in " + markdown.relative_to(directory).as_posix()
        try:
            url = urlparse(target)
        except ValueError as exc:
            raise ValidationError(field + ": malformed destination") from exc
        if url.scheme == "https" and url.netloc:
            return
        require(not url.scheme and not url.netloc, field + ": only self-contained local paths or HTTPS links are allowed")
        decoded = unquote(url.path)
        require("\\" not in decoded and "\x00" not in decoded and not Path(decoded).is_absolute(),
                field + ": unsafe local path")
        path = no_symlinks(markdown.parent / decoded)
        resolved = path.resolve()
        require(resolved == directory.resolve() or directory.resolve() in resolved.parents,
                field + ": local reference escapes skill directory")
        require(path.is_file() or path.is_dir(), field + ": missing target " + target)

    for parent, dirs, files in os.walk(directory, followlinks=False, onerror=walk_error):
        for name in dirs + files:
            path = no_symlinks(Path(parent) / name)
            require(path.is_dir() or path.is_file(), "skill.reference: unsupported resource")
        for name in files:
            markdown = Path(parent) / name
            if markdown.suffix.lower() != ".md":
                continue
            content = _markdown_without_code(markdown.read_text(encoding="utf-8"))
            definitions = {}
            for match in re.finditer(r"(?m)^ {0,3}\[([^\]\n]+)\]:[ \t]*(?:\n[ \t]+)?([^\n]+)", content):
                key = " ".join(match.group(1).split()).casefold()
                target = _markdown_destination(match.group(2))
                definitions[key] = target
                check_reference(markdown, target)
            for match in re.finditer(r"!?\[(?:\\.|[^\]\\])*\]\(", content):
                check_reference(markdown, _markdown_destination(content[match.end():]))
            for match in re.finditer(r"!?\[([^\]\n]+)\]\[([^\]\n]*)\]", content):
                key = " ".join((match.group(2) or match.group(1)).split()).casefold()
                require(key in definitions, "skill.reference: undefined reference label " + key)


def validate(profile, workflow, catalog, catalog_root):
    try:
        _validate(profile, workflow, catalog, Path(catalog_root))
    except (OSError, UnicodeError, RecursionError) as exc:
        raise ValidationError("validation: " + str(exc)) from exc


def validate_profile_tracker(profile):
    try:
        _validate_profile_tracker(profile)
    except (OSError, UnicodeError, RecursionError) as exc:
        raise ValidationError("validation: " + str(exc)) from exc


def _validate_profile_tracker(profile):
    shape(profile, "schema_version customer_id name sdlc glossary systems issue_tracker roles pains success_criteria "
          "constraints facts assumptions unknowns", "profile")
    _version(profile["schema_version"], "profile")
    identifier(profile["customer_id"], "profile.customer_id")
    text(profile["name"], "profile.name")
    for row in objects(profile["sdlc"], "profile.sdlc", True):
        shape(row, "stage current desired", "profile.sdlc")
        for key in row:
            text(row[key], "profile.sdlc." + key)
    require(isinstance(profile["glossary"], dict), "profile.glossary: expected string map")
    for key, value in profile["glossary"].items():
        text(key, "profile.glossary.key")
        text(value, "profile.glossary." + key)
    for key in ("roles", "success_criteria", "constraints", "assumptions", "unknowns"):
        strings(profile[key], "profile." + key, key in ("roles", "success_criteria"))
    for row in objects(profile["pains"], "profile.pains"):
        shape(row, "description impact frequency", "profile.pains")
        for key in row:
            text(row[key], "profile.pains." + key)
    facts = objects(profile["facts"], "profile.facts")
    for row in facts:
        shape(row, "id statement evidence", "profile.facts")
        for key in row:
            text(row[key], "profile.facts." + key)
    _unique(facts, "profile.facts")
    systems = objects(profile["systems"], "profile.systems")
    known_tools = set()
    for system in systems:
        shape(system, "id kind tool capabilities", "profile.systems")
        identifier(system["id"], "profile.systems.id")
        text(system["kind"], "profile.systems.kind")
        text(system["tool"], "profile.systems.tool")
        require(SYSTEM_TOKEN.fullmatch(system["tool"]),
                "profile.systems.tool: expected CLI token, skill:name, or mcp:name, not a command")
        strings(system["capabilities"], "profile.systems.capabilities", True, True)
        known_tools.update(system["id"] + "." + c for c in system["capabilities"])
    by_system = _unique(systems, "profile.systems")

    tracker = profile["issue_tracker"]
    shape(
        tracker,
        "system_id provider connection project path skill mcp capabilities",
        "profile.issue_tracker",
    )
    identifier(tracker["system_id"], "profile.issue_tracker.system_id")
    require(tracker["system_id"] in by_system, "profile.issue_tracker.system_id: unknown system")
    text(tracker["provider"], "profile.issue_tracker.provider")
    require(tracker["provider"] in TRACKER_PROVIDERS, "profile.issue_tracker.provider: invalid provider")
    text(tracker["connection"], "profile.issue_tracker.connection")
    require(tracker["connection"] in TRACKER_CONNECTIONS, "profile.issue_tracker.connection: invalid connection")
    tracker_project(tracker["project"], tracker["provider"])
    optional_text(tracker["path"], "profile.issue_tracker.path")
    optional_text(tracker["skill"], "profile.issue_tracker.skill")
    optional_text(tracker["mcp"], "profile.issue_tracker.mcp")
    strings(tracker["capabilities"], "profile.issue_tracker.capabilities", True, True)
    require(set(tracker["capabilities"]) <= TRACKER_CAPABILITIES,
            "profile.issue_tracker.capabilities: invalid capability")
    system = by_system[tracker["system_id"]]
    require(set(tracker["capabilities"]) <= set(system["capabilities"]),
            "profile.issue_tracker.capabilities: missing from linked system")
    tracker_tools = {
        tracker["system_id"] + "." + capability
        for capability in tracker["capabilities"]
    }
    tracker_write_tools = {
        tracker["system_id"] + "." + capability
        for capability in set(tracker["capabilities"]) & TRACKER_WRITE_CAPABILITIES
    }

    if tracker["provider"] == "markdown":
        require(tracker["connection"] == "local",
                "profile.issue_tracker.connection: markdown requires local")
        path = tracker["path"]
        require(
            isinstance(path, str)
            and bool(path.strip())
            and not Path(path).is_absolute()
            and "\\" not in path
            and all(part not in ("", ".", "..") for part in path.split("/")),
            "profile.issue_tracker.path: unsafe relative path",
        )
        require(tracker["skill"] is None and tracker["mcp"] is None,
                "profile.issue_tracker: markdown cannot declare skill or mcp")
        require(system["tool"] == "git",
                "profile.issue_tracker: markdown system tool must be git")
    else:
        require(tracker["path"] is None,
                "profile.issue_tracker.path: only markdown uses a path")
        require(tracker["connection"] != "local",
                "profile.issue_tracker.connection: remote provider cannot be local")
        if tracker["connection"] == "skill":
            identifier(tracker["skill"], "profile.issue_tracker.skill")
            require(system["tool"] == "skill:" + tracker["skill"],
                    "profile.issue_tracker.skill: system tool mismatch")
            if tracker["mcp"] is not None:
                require(re.fullmatch(r"mcp:[a-z][a-z0-9-]*\Z", tracker["mcp"]),
                        "profile.issue_tracker.mcp: expected mcp:name")
        else:
            require(tracker["skill"] is None,
                    "profile.issue_tracker.skill: mcp connection cannot declare skill")
            require(isinstance(tracker["mcp"], str) and
                    re.fullmatch(r"mcp:[a-z][a-z0-9-]*\Z", tracker["mcp"]),
                    "profile.issue_tracker.mcp: expected mcp:name")
            require(system["tool"] == tracker["mcp"],
                    "profile.issue_tracker.mcp: system tool mismatch")

    return known_tools, tracker, tracker_tools, tracker_write_tools


def _validate(profile, workflow, catalog, root):
    from .skill_bundle import validate_skill_bundle

    known_tools, tracker, tracker_tools, tracker_write_tools = _validate_profile_tracker(profile)

    shape(catalog, "schema_version skills", "catalog")
    _version(catalog["schema_version"], "catalog")
    skills = objects(catalog["skills"], "catalog.skills", True)
    for skill in skills:
        shape(skill, "id path description inputs outputs requires effects source compatibility", "catalog.skills")
        identifier(skill["id"], "catalog.skills.id")
        text(skill["description"], "catalog.skills.description")
        directory = relative_path(root, skill["path"], "catalog.skills.path", True)
        entry = relative_path(directory, "SKILL.md", "catalog.skills.path.SKILL.md").read_text(encoding="utf-8")
        require(entry.startswith("---\n") and "\n---\n" in entry[4:],
                "catalog.skills.path.SKILL.md: expected YAML frontmatter")
        header = entry.split("\n---\n", 1)[0]
        name = re.search(r"^name:\s*(.+)$", header, re.MULTILINE)
        description = re.search(r"^description:\s*(.+)$", header, re.MULTILINE)
        require(name is not None and name.group(1).strip().strip("\"'") == skill["id"],
                "catalog.skills.path.SKILL.md: name must match skill id")
        require(description is not None and bool(description.group(1).strip().strip("\"'")),
                "catalog.skills.path.SKILL.md: nonempty description required")
        for child in directory.rglob("*"):
            no_symlinks(child)
            require(child.is_dir() or child.is_file(), "catalog.skills.path: unsupported file")
        _validate_skill_references(directory)
        validate_skill_bundle(directory, skill["id"])
        for key in ("inputs", "outputs"):
            strings(skill[key], "catalog.skills." + key, ids=True)
        strings(skill["requires"], "catalog.skills.requires")
        for tool in skill["requires"]:
            require(TOOL.fullmatch(tool), "catalog.skills.requires: expected system.capability")
        strings(skill["effects"], "catalog.skills.effects", True)
        require(set(skill["effects"]) <= EFFECTS, "catalog.skills.effects: invalid effect")
        source = skill["source"]
        shape(source, "url revision path license license_file", "catalog.skills.source")
        for key in source:
            text(source[key], "catalog.skills.source." + key)
        try:
            url = urlparse(source["url"])
        except ValueError as exc:
            raise ValidationError("catalog.skills.source.url: malformed URL") from exc
        require(url.scheme == "https" and bool(url.netloc) and url.username is None and url.password is None,
                "catalog.skills.source.url: expected https URL without credentials")
        require(re.fullmatch("[0-9a-fA-F]{40}", source["revision"]),
                "catalog.skills.source.revision: expected 40-character commit hash")
        require(source["license"] == "MIT", "catalog.skills.source.license: expected MIT")
        require(not Path(source["path"]).is_absolute() and "\\" not in source["path"] and
                all(p not in ("", ".", "..") for p in source["path"].split("/")),
                "catalog.skills.source.path: unsafe relative upstream path")
        license_path = relative_path(root, source["license_file"], "catalog.skills.source.license_file")
        require(bool(license_path.read_text(encoding="utf-8").strip()), "catalog.skills.source.license_file: empty license")
        compatibility = skill["compatibility"]
        shape(compatibility, "runtime status evidence", "catalog.skills.compatibility")
        require(compatibility["runtime"] == "copilot-cli", "catalog.skills.compatibility.runtime: expected copilot-cli")
        require(compatibility["status"] in ("verified", "candidate", "unverified"),
                "catalog.skills.compatibility.status: invalid status")
        evidence = relative_path(root, compatibility["evidence"], "catalog.skills.compatibility.evidence")
        require(bool(evidence.read_text(encoding="utf-8").strip()), "catalog.skills.compatibility.evidence: empty report")
    by_skill = _unique(skills, "catalog.skills")
    if tracker["connection"] == "local":
        require(
            "hf-issues-markdown" in by_skill,
            "catalog.skills: local tracker requires hf-issues-markdown",
        )
        markdown_skill = by_skill["hf-issues-markdown"]
        require(
            markdown_skill["compatibility"]["status"] == "verified",
            "catalog.skills.compatibility.status: selected skill must be verified",
        )
        _validate_evidence(root, markdown_skill)

    shape(workflow, "schema_version id name customer_id goal trigger inputs outputs customer_rules approved steps traceability",
          "workflow")
    _version(workflow["schema_version"], "workflow")
    identifier(workflow["id"], "workflow.id")
    require(workflow["customer_id"] == profile["customer_id"], "workflow.customer_id: customer mismatch")
    for key in ("name", "goal", "trigger"):
        text(workflow[key], "workflow." + key)
    for key in ("inputs", "outputs"):
        strings(workflow[key], "workflow." + key, True, True)
    strings(workflow["customer_rules"], "workflow.customer_rules")
    shape(workflow["approved"], "by at", "workflow.approved")
    for key in ("by", "at"):
        text(workflow["approved"][key], "workflow.approved." + key)
    try:
        approved_at = datetime.fromisoformat(workflow["approved"]["at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("workflow.approved.at: expected ISO date-time with timezone") from exc
    require(approved_at.tzinfo is not None, "workflow.approved.at: timezone is required")
    steps = objects(workflow["steps"], "workflow.steps", True)
    verified_skills = set()
    for step in steps:
        shape(step, "id name skill needs inputs outputs tools effect approval approver completion failure manual",
              "workflow.steps", optional="approval_timing")
        identifier(step["id"], "workflow.steps.id")
        for key in ("name", "skill", "completion", "failure"):
            text(step[key], "workflow.steps." + key)
        for key in ("needs", "inputs", "outputs"):
            strings(step[key], "workflow.steps." + key, ids=True)
        strings(step["tools"], "workflow.steps.tools")
        for tool in step["tools"]:
            require(TOOL.fullmatch(tool), "workflow.steps.tools: expected system.capability")
        tracker_bindings = {
            tool for tool in step["tools"]
            if (
                tool.startswith(tracker["system_id"] + ".")
                and tool.split(".", 1)[1] in TRACKER_CAPABILITIES
            )
        }
        require(
            tracker_bindings <= tracker_tools,
            "workflow.steps.tools: tracker binding missing from profile.issue_tracker.capabilities",
        )
        require(isinstance(step["effect"], str) and step["effect"] in EFFECTS, "workflow.steps.effect: invalid effect")
        require(type(step["approval"]) is bool, "workflow.steps.approval: expected boolean")
        if set(step["tools"]) & tracker_write_tools:
            if tracker["provider"] == "markdown":
                require(
                    (step["effect"] == "local" and step["approval"] is True) or
                    (step["effect"] == "manual" and step["manual"] is not None),
                    "workflow.steps: Markdown tracker write requires approved local change or manual handoff",
                )
            else:
                require(
                    (step["effect"] == "external-write" and step["approval"] is True) or
                    (step["effect"] == "manual" and step["manual"] is not None),
                    "workflow.steps: tracker write requires approved external-write or manual handoff",
                )
        timing = step.get("approval_timing", "before")
        require(timing in ("before", "after"), "workflow.steps.approval_timing: expected before or after")
        if timing == "after":
            require(step["approval"] and step["effect"] in ("read", "local"),
                    "workflow.steps.approval_timing: after requires a gated read/local step")
        if step["effect"] == "external-write":
            require(step["approval"], "workflow.steps.approval: external write requires approval")
        if step["approval"]:
            text(step["approver"], "workflow.steps.approver")
        else:
            require(step["approver"] is None or step["approver"] == "",
                    "workflow.steps.approver: must be null or empty without approval")
        if step["manual"] is not None:
            shape(step["manual"], "owner instructions resume_when", "workflow.steps.manual")
            for key in step["manual"]:
                text(step["manual"][key], "workflow.steps.manual." + key)
            require(step["effect"] in ("manual", "external-write"),
                    "workflow.steps.manual: handoff requires manual or external-write effect")
        if step["effect"] == "manual":
            require(step["manual"] is not None, "workflow.steps.manual: handoff required")
        if set(step["tools"]) - known_tools:
            require(step["manual"] is not None, "workflow.steps.tools: unknown tools require explicit manual handoff")
        require(step["skill"] in by_skill, "workflow.steps.skill: unknown skill")
        skill = by_skill[step["skill"]]
        require(skill["compatibility"]["status"] == "verified", "catalog.skills.compatibility.status: selected skill must be verified")
        if skill["id"] not in verified_skills:
            _validate_evidence(root, skill)
            _validate_skill_references(root / skill["path"])
            verified_skills.add(skill["id"])
        require(step["effect"] in skill["effects"], "workflow.steps.effect: incompatible skill effect")
        require(set(skill["requires"]) <= set(step["tools"]), "workflow.steps.tools: missing skill requires")
    by_step = _unique(steps, "workflow.steps")
    ancestors = {}
    visiting = set()

    def visit(step_id):
        require(step_id not in visiting, "workflow.steps.needs: dependency cycle")
        if step_id in ancestors:
            return ancestors[step_id]
        visiting.add(step_id)
        result = set()
        for dep in by_step[step_id]["needs"]:
            require(dep in by_step, "workflow.steps.needs: unknown step " + dep)
            result.add(dep)
            result.update(visit(dep))
        visiting.remove(step_id)
        ancestors[step_id] = result
        return result

    produced = set(workflow["inputs"])
    for step in steps:
        available = set(workflow["inputs"])
        for ancestor in visit(step["id"]):
            available.update(by_step[ancestor]["outputs"])
        require(set(step["inputs"]) <= available, "workflow.steps.inputs: artifact is not supplied by inputs or ancestors")
        produced.update(step["outputs"])
    require(set(workflow["outputs"]) <= produced, "workflow.outputs: artifact is not produced")
    for row in objects(workflow["traceability"], "workflow.traceability", True):
        shape(row, "requirement steps checks", "workflow.traceability")
        text(row["requirement"], "workflow.traceability.requirement")
        strings(row["steps"], "workflow.traceability.steps", True, True)
        require(set(row["steps"]) <= set(by_step), "workflow.traceability.steps: unknown step")
        strings(row["checks"], "workflow.traceability.checks", True)
