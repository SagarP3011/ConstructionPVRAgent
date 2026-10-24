"""Command line interface: `python -m pvr.cli <command>`.

Commands:
    check-llm   Confirm the OpenAI key works and OPENAI_MODEL supports tool calling.
    engines     Deterministic assessment for the three default changes (no LLM).
    agent       Run one agent alone, live (for example: agent cost --change wall_height).
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


def cmd_agent(args: argparse.Namespace) -> int:
    """Run one agent alone, live, and print its tool calls, message and claim check."""
    from pvr.config import RUNS_DIR
    from pvr.data_loader import get_data
    from pvr.engines.change import make_context
    from pvr.engines.common import EngineError
    from pvr.llm.client import LLMError, OpenAILLM
    from pvr.models import Event
    from pvr.orchestrator.single_agent import run_single_agent

    settings = load_settings()
    data = get_data()
    try:
        mode = args.mode or data.change_type(args.change).modes[0]
        ctx = make_context(data, args.change, _parse_params(args.param), mode=mode)
        llm = OpenAILLM(settings)
    except (EngineError, KeyError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"Running the {args.name} agent on {ctx.change_type} ({ctx.mode}) with {settings.openai_model} ...")

    def show(event: Event) -> None:
        p = event.payload
        if event.type == "tool.called" and p["agent"] != "orchestrator":
            print(f"  -> {p['tool']}({', '.join(f'{k}={v!r}' for k, v in p['args'].items()) if p['tool'] != 'post_message' else '...'})")
        elif event.type == "tool.result" and p["agent"] != "orchestrator" and not p["ok"]:
            print(f"     error: {p['error']}")
        elif event.type == "llm.call":
            print(f"  [model {p['model']}: {p['prompt_tokens']} in / {p['completion_tokens']} out tokens, "
                  f"{p['latency_ms']} ms]")

    session, turn = run_single_agent(args.name, ctx, data, settings, llm, sinks=[show])

    print()
    if turn.message is None:
        print(f"Turn failed: {turn.error}")
    else:
        m = turn.message
        print(f"{m.message_id} {m.from_agent} -> {m.to} ({m.intent}), stance {m.stance}")
        print(m.content)
        print("Claims:")
        bad = 0
        for c in m.claims:
            problem = session.facts.check_claim(c.fact_id, c.value, c.unit)
            bad += problem is not None
            print(f"  {'OK ' if problem is None else 'BAD'} {c.label} = {c.value} {c.unit} [{c.fact_id}]"
                  + (f"  ({problem})" if problem else ""))
        print(f"Claims checked against the fact registry: {len(m.claims) - bad} ok, {bad} with problems")
    print(f"Steps {turn.steps}{' (forced)' if turn.forced else ''}; tokens {turn.prompt_tokens} in / "
          f"{turn.completion_tokens} out; facts registered {len(session.facts)}")
    print(f"Trace: {RUNS_DIR / session.run_id / 'events.jsonl'}")
    return 0 if turn.status == "posted" else 1


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

    agent = sub.add_parser("agent", help="Run one agent alone, live, with earlier stages pre-filled from engines.")
    agent.add_argument("name", help="Agent name, for example cost")
    agent.add_argument("--change", required=True, help="Change type, for example wall_height")
    agent.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                       help="Parameter value, repeatable (defaults otherwise)")
    agent.add_argument("--mode", choices=["internal_what_if", "contractor_pvr"],
                       help="Mode (default: the first mode of the change type)")
    agent.set_defaults(func=cmd_agent)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
