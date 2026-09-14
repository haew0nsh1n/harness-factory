import argparse
import json
from pathlib import Path
import sys

from .contracts import load_json, validate, validate_profile_tracker
from .errors import HarnessError
from .evaluation import delivery_check, seal_evaluation
from .install import apply_install, plan_install
from .package import check_package, generate_package
from .preflight import preflight
from .records import STATUSES, record
from .tracker import tracker_guide


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise HarnessError("arguments: " + message)


def parser():
    root = Parser(description="Validate and deliver bounded customer workflow packages.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("validate", "generate"):
        command = commands.add_parser(name)
        for flag in ("profile", "workflow", "catalog"):
            command.add_argument("--" + flag, required=True, type=Path)
        if name == "generate":
            command.add_argument("--scenarios", required=True, type=Path)
            command.add_argument("--output", required=True, type=Path)
    command = commands.add_parser("evaluate")
    command.add_argument("--package", required=True, type=Path)
    command.add_argument("--results", required=True, type=Path)
    command = commands.add_parser("delivery-check")
    command.add_argument("--package", required=True, type=Path)
    command.add_argument("--allow-read-probes", action="store_true")
    command = commands.add_parser("tracker-guide")
    command.add_argument("--profile", required=True, type=Path)
    command.add_argument("--target", type=Path, default=Path("."))
    for name in ("check", "install", "preflight", "record"):
        command = commands.add_parser(name)
        command.add_argument("--package", required=True, type=Path)
        if name == "install":
            command.add_argument("--target", required=True, type=Path)
            command.add_argument("--approve")
        elif name == "preflight":
            command.add_argument("--allow-read-probes", action="store_true")
        elif name == "record":
            command.add_argument("--run", required=True)
            command.add_argument("--step", required=True)
            command.add_argument("--status", required=True, choices=STATUSES)
            command.add_argument("--evidence")
            command.add_argument("--decision", choices=("approved", "denied"))
            command.add_argument("--by")
    return root


def main(argv=None):
    try:
        args = parser().parse_args(argv)
        if args.command in ("validate", "generate"):
            profile, workflow, catalog = (load_json(p) for p in (args.profile, args.workflow, args.catalog))
            if args.command == "validate":
                validate(profile, workflow, catalog, args.catalog.parent)
                result = {"ok": True, "operation": "validate"}
            else:
                scenarios = load_json(args.scenarios)
                result = generate_package(
                    profile, workflow, scenarios, catalog, args.catalog.parent, args.output
                )
        elif args.command == "evaluate":
            results = load_json(args.results)
            results_bytes = args.results.read_bytes()
            result = seal_evaluation(
                args.package,
                results,
                results_bytes=results_bytes,
            )
        elif args.command == "check":
            result = check_package(args.package)
        elif args.command == "delivery-check":
            result = delivery_check(args.package, args.allow_read_probes)
        elif args.command == "install":
            result = (apply_install(args.package, args.target, args.approve) if args.approve is not None
                      else plan_install(args.package, args.target))
        elif args.command == "preflight":
            result = preflight(args.package, args.allow_read_probes)
        elif args.command == "tracker-guide":
            profile = load_json(args.profile)
            validate_profile_tracker(profile)
            result = tracker_guide(profile, args.target)
        else:
            result = record(args.package, args.run, args.step, args.status, args.evidence, args.decision, args.by)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False))
        return 0
    except (HarnessError, OSError, UnicodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc), "type": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
