"""Extensible CLI subcommands.

Each module in this package exposes:

    def register(subparsers, formatter_class) -> None

The CLI loader discovers modules here automatically.
"""
