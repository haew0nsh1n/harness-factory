from pathlib import Path

from .contracts import load_json, no_symlinks, require
from .errors import HarnessError, InstallError
from .package import MANIFEST, atomic_write, check_package, hash_bytes, inventory, json_bytes, managed_inventory


def _plan(package, target):
    package, target = no_symlinks(package), no_symlinks(target)
    source, destination = package.resolve(), target.resolve()
    require(source != destination and source not in destination.parents and destination not in source.parents,
            "install: source and target roots overlap")
    checked = check_package(package)
    require(checked["mode"] == "distribution", "install source: a distribution is required, not an installed receipt")
    manifest = load_json(package / MANIFEST)
    require(not target.exists() or target.is_dir(), "install.target: expected directory")
    source_files = inventory(package)
    source_files[MANIFEST] = hash_bytes((package / MANIFEST).read_bytes())
    directories = []
    target_files = managed_inventory(target, manifest["owned_prefixes"], directories) if target.exists() else {}
    if (target / MANIFEST).exists():
        target_files[MANIFEST] = hash_bytes((target / MANIFEST).read_bytes())
    extras = set(target_files) - set(source_files)
    require(not extras, "install: unlisted files collide with newly owned directories: " + ", ".join(sorted(extras)))
    files = []
    installed_manifest = dict(manifest, mode="installed")
    for relative, digest in sorted(source_files.items()):
        path = no_symlinks(target / relative)
        require(not path.is_dir(), "install: file collides with directory " + relative)
        for ancestor in path.parents:
            if ancestor == target:
                break
            require(not ancestor.exists() or ancestor.is_dir(), "install: parent collides with file " + str(ancestor))
        old = target_files.get(relative)
        if relative == MANIFEST:
            digest = hash_bytes(json_bytes(installed_manifest))
        files.append({"path": relative, "action": "create" if old is None else
                      ("unchanged" if old == digest else "replace")})
    binding = {"source": str(source), "source_files": source_files, "target": str(destination),
               "target_exists": target.exists(), "target_files": target_files, "target_directories": sorted(directories)}
    return {"ok": True, "operation": "install-preview", "package": str(source), "target": str(destination),
            "digest": hash_bytes(json_bytes(binding)), "files": files}, source_files, target_files


def plan_install(package, target):
    try:
        return _plan(Path(package), Path(target))[0]
    except (HarnessError, OSError, UnicodeError) as exc:
        raise InstallError("install preview: " + str(exc)) from exc


def apply_install(package, target, digest):
    written = []
    mutated = False
    try:
        require(isinstance(digest, str) and bool(digest), "install approval: current digest required")
        preview, source_hashes, target_hashes = _plan(Path(package), Path(target))
        require(digest == preview["digest"], "install approval: stale or incorrect digest; preview again")
        package, target = Path(preview["package"]), Path(preview["target"])
        payload = {}
        for relative, expected in source_hashes.items():
            data = (no_symlinks(package / relative)).read_bytes()
            require(hash_bytes(data) == expected, "install: source changed after approval")
            payload[relative] = data
        require(_plan(package, target)[0]["digest"] == digest, "install approval: state changed; preview again")
        manifest = load_json(package / MANIFEST)
        manifest["mode"] = "installed"
        payload[MANIFEST] = json_bytes(manifest)
        no_symlinks(target)
        target.mkdir(parents=True, exist_ok=True)
        mutated = True
        for relative in sorted(payload, key=lambda value: (value == MANIFEST, value)):
            path = no_symlinks(target / relative)
            old = hash_bytes(path.read_bytes()) if path.is_file() else None
            require(old == target_hashes.get(relative), "install: target changed during apply: " + relative)
            if old == hash_bytes(payload[relative]):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(path, payload[relative])
            written.append(relative)
        check_package(target)
        return {"ok": True, "operation": "install", "target": str(target),
                "digest": digest, "written": written}
    except (HarnessError, OSError, UnicodeError) as exc:
        prefix = "partial install (no rollback; {} files written): ".format(len(written)) if mutated else "install: "
        raise InstallError(prefix + str(exc)) from exc
