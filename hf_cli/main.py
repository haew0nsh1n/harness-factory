from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from hf_cli.auth import AuthSession, remove_saved_session
from hf_cli.cache import default_cache_root
from hf_cli.client import RegistryClient
from hf_cli.config import (
    DevelopmentIdentity,
    RegistryConfig,
    load_config,
    save_config,
    validate_registry_url,
)
from hf_cli.errors import CliError
from hf_cli.install import install_workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hf")
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", help="authenticate to a registry")
    login.add_argument("--registry", required=True)
    login.add_argument("--tenant")
    login.add_argument("--client-id")
    login.add_argument("--scope")
    login.add_argument("--development", action="store_true")
    login.add_argument("--organization")
    login.add_argument("--subject")
    login.add_argument("--role", action="append", dest="roles")
    login.add_argument("--json", action="store_true")

    logout = subparsers.add_parser("logout", help="remove the saved login session")
    logout.add_argument("--json", action="store_true")

    search = subparsers.add_parser("search", help="search published workflows")
    search.add_argument("query")
    search.add_argument("--json", action="store_true")

    info = subparsers.add_parser("info", help="show workflow information")
    info.add_argument("reference", metavar="SLUG[@VERSION]")
    info.add_argument("--json", action="store_true")

    install = subparsers.add_parser("install", help="install a published workflow")
    install.add_argument("reference", metavar="SLUG@VERSION")
    install.add_argument("--target", required=True, type=Path)
    install.add_argument("--approve")
    install.add_argument("--json", action="store_true")
    return parser


def _login_config(args: argparse.Namespace) -> tuple[RegistryConfig, DevelopmentIdentity | None]:
    url = validate_registry_url(args.registry, development=args.development)
    if args.development:
        if not args.organization or not args.subject or not args.roles:
            raise CliError(
                "invalid_arguments",
                "development login requires --organization, --subject, and --role",
            )
        if args.tenant or args.client_id or args.scope:
            raise CliError(
                "invalid_arguments",
                "development login does not accept tenant, client ID, or scope",
            )
        return (
            RegistryConfig(
                url=url,
                tenant_id="development",
                client_id="development",
                scope="development",
                development=True,
            ),
            DevelopmentIdentity(
                organization=args.organization,
                subject=args.subject,
                roles=tuple(args.roles),
            ),
        )
    if args.organization or args.subject or args.roles:
        raise CliError(
            "invalid_arguments",
            "development identity arguments require --development",
        )
    if not args.tenant or not args.client_id or not args.scope:
        raise CliError(
            "invalid_arguments",
            "production login requires --tenant, --client-id, and --scope",
        )
    return (
        RegistryConfig(
            url=url,
            tenant_id=args.tenant,
            client_id=args.client_id,
            scope=args.scope,
        ),
        None,
    )


def _print_result(value: object, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"ok": True, "result": value}, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                print(item.get("slug", json.dumps(item, sort_keys=True)))
            else:
                print(item)
    elif isinstance(value, dict):
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        print(value)


def run(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "login":
            config, identity = _login_config(args)
            auth = AuthSession(
                config,
                development_identity=identity,
                notifier=lambda message: print(message, file=sys.stderr),
            )
            auth.login()
            actor = RegistryClient(config, auth).whoami()
            save_config(config, development_identity=identity)
            _print_result({"authenticated": True, "actor": actor}, as_json=args.json)
            return 0

        loaded = load_config(include_development_identity=True)
        config, identity = loaded
        if args.command == "logout":
            remove_saved_session(config)
            _print_result({"logged_out": True}, as_json=args.json)
            return 0
        auth = AuthSession(config, development_identity=identity)
        client = RegistryClient(config, auth)
        if args.command == "search":
            _print_result(client.search(args.query), as_json=args.json)
            return 0
        slug, separator, version = args.reference.rpartition("@")
        if not separator:
            slug, version = args.reference, None
        elif not slug or not version:
            raise CliError(
                "invalid_reference",
                "asset reference must be SLUG or SLUG@MAJOR.MINOR.PATCH",
            )
        if args.command == "install":
            if not separator or version is None:
                raise CliError(
                    "invalid_reference",
                    "install reference must be SLUG@MAJOR.MINOR.PATCH",
                )
            _print_result(
                install_workflow(
                    client,
                    slug,
                    version,
                    args.target,
                    default_cache_root(),
                    args.approve,
                ),
                as_json=args.json,
            )
            return 0
        _print_result(client.info(slug, version), as_json=args.json)
        return 0
    except CliError as error:
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": error.message,
                        "code": error.code,
                    },
                    sort_keys=True,
                ),
                file=sys.stderr,
            )
        else:
            print(f"hf: {error.message} [{error.code}]", file=sys.stderr)
        return 1


def main() -> int:
    return run()
