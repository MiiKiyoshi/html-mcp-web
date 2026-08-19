"""Command-line entry points for html-mcp-web."""

import argparse
import json
import sys
from pathlib import Path

import yaml

from .config import (
    DEFAULT_CONFIG_NAME,
    Config,
    create_config,
    load_config,
)


def cmd_init(args: argparse.Namespace) -> int:
    target = Path.cwd() / DEFAULT_CONFIG_NAME
    try:
        created = create_config(layout=args.layout, main=args.main, port=args.port, output_path=target,
                                template=args.template, content=args.content)
    except (FileExistsError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(created)
    return 0


def _parse_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def cmd_config(args: argparse.Namespace) -> int:
    config = load_config()
    if config.config_path is None:
        print(f"{DEFAULT_CONFIG_NAME} was not found", file=sys.stderr)
        return 1
    if args.key is None:
        print(config.config_path)
        print(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
        return 0
    data = config.to_dict()
    parts = args.key.split(".")
    target = data
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            print(f"unknown configuration key: {args.key}", file=sys.stderr)
            return 1
        target = target[part]
    leaf = parts[-1]
    if leaf not in target:
        print(f"unknown configuration key: {args.key}", file=sys.stderr)
        return 1
    if args.value is None:
        value = target[leaf]
        print(json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value)
        return 0
    if args.key in {"watch", "ignore"}:
        target[leaf] = _parse_list(args.value)
    elif args.key == "port":
        target[leaf] = int(args.value)
    else:
        target[leaf] = args.value
    validated = Config.from_dict(data, config.config_path)
    config.config_path.write_text(yaml.safe_dump(validated.to_dict(), sort_keys=False), encoding="utf-8")
    print(config.config_path)
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    from .mcp_server import main as run_mcp

    run_mcp(Path.cwd())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="html-mcp-web")
    subcommands = parser.add_subparsers(dest="command")

    init = subcommands.add_parser("init")
    init.add_argument("--layout", required=True, choices=["slides", "report"])
    init.add_argument("--main", default="artifact.html")
    init.add_argument("--port", type=int, default=8765)
    init.add_argument("--template", help="template directory name; --content is then required")
    init.add_argument("--content", help="content file the template compiles into --main")
    init.set_defaults(handler=cmd_init)

    config = subcommands.add_parser("config")
    config.add_argument("key", nargs="?")
    config.add_argument("value", nargs="?")
    config.set_defaults(handler=cmd_config)

    mcp = subcommands.add_parser("mcp")
    mcp.set_defaults(handler=cmd_mcp)
    return parser


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not values:
        parser.print_help()
        return 0
    args = parser.parse_args(values)
    return args.handler(args)


def main_mcp(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    return main(["mcp", *values])
