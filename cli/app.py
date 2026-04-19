from __future__ import annotations

import argparse
import asyncio
import importlib
import logging
import pkgutil

from cli import commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
)
log = logging.getLogger("cli")


class HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawDescriptionHelpFormatter,
):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codectx",
        description=(
            "Shared context graph CLI for serving, querying, and evaluating repository symbol context."
        ),
        formatter_class=HelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    subparsers.required = True

    for _, module_name, _ in pkgutil.iter_modules(commands.__path__):
        module = importlib.import_module(f"{commands.__name__}.{module_name}")
        register = getattr(module, "register", None)
        if register is not None:
            register(subparsers, HelpFormatter)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1

    try:
        result = handler(args)
        if asyncio.iscoroutine(result):
            return asyncio.run(result) or 0
        return int(result or 0)
    except KeyboardInterrupt:
        log.info("command stopped")
        return 130
