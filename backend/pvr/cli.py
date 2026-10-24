"""Command line interface: `python -m pvr.cli <command>`.

Commands:
    check-llm   Confirm the OpenAI key works and OPENAI_MODEL supports tool calling.
"""

from __future__ import annotations

import argparse
import sys

from pvr.config import load_settings


def _yes_no(value: bool | None) -> str:
    """Format a tri-state flag for the console."""
    return "unknown" if value is None else ("yes" if value else "no")


def cmd_check_llm(_: argparse.Namespace) -> int:
    """Print the LLM connectivity check. Returns a process exit code."""
    from pvr.llm.check import check_llm

    result = check_llm(load_settings())
    print("OpenAI connectivity check")
    print(f"  API key configured : {_yes_no(result.key_configured)}")
    print(f"  API key works      : {_yes_no(result.key_works)}")
    if result.key_works:
        print(f"  Models visible     : {result.models_visible}")
    for m in result.models:
        print(f"  Model {m.model}")
        print(f"    available        : {_yes_no(m.available)}")
        print(f"    tool calling     : {_yes_no(m.supports_tool_calling)}")
        if m.detail:
            print(f"    detail           : {m.detail}")
    if result.error:
        print(f"  Problem            : {result.error}")
    print("Result:", "OK" if result.ok else "NOT OK")
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="pvr", description="PVR Agent Room command line tools.")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-llm", help="Check the OpenAI key and that OPENAI_MODEL supports tool calling.")
    check.set_defaults(func=cmd_check_llm)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
