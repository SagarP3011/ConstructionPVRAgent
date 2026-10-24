"""Command line interface: `python -m pvr.cli <command>`.

Commands:
    check-llm   Confirm the OpenAI key works and OPENAI_MODEL supports tool calling.
    engines     Deterministic assessment for the three default changes (no LLM).
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


def _parse_params(pairs: list[str]) -> dict[str, float]:
    """Parse `name=value` pairs into parameters."""
    params: dict[str, float] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep:
            raise SystemExit(f"Parameters must look like name=value; got {pair}")
        params[name.strip()] = float(value)
    return params


def cmd_engines(args: argparse.Namespace) -> int:
    """Print the deterministic assessment for each default case, or for one given change."""
    from pvr.data_loader import get_data
    from pvr.engines.change import make_context
    from pvr.engines.common import EngineError
    from pvr.report import assessment_report

    data = get_data()
    if args.change:
        runs = [(args.change, _parse_params(args.param), args.mode)]
    else:
        # Defaults: the wall in contractor PVR mode (it has a claim to check), the others as what-ifs.
        runs = [(ct.id, {}, ct.modes[0]) for ct in data.scenario.change_types]
    try:
        reports = [assessment_report(make_context(data, ct, params, mode=mode), data) for ct, params, mode in runs]
    except EngineError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print("\n\n".join(reports))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(prog="pvr", description="PVR Agent Room command line tools.")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check-llm", help="Check the OpenAI key and that OPENAI_MODEL supports tool calling.")
    check.set_defaults(func=cmd_check_llm)

    engines = sub.add_parser("engines", help="Deterministic assessment (no LLM) for the three default changes.")
    engines.add_argument("--change", help="One change type, for example wall_height")
    engines.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                         help="Parameter value, repeatable (with --change)")
    engines.add_argument("--mode", default="internal_what_if", choices=["internal_what_if", "contractor_pvr"],
                         help="Mode (with --change)")
    engines.set_defaults(func=cmd_engines)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
