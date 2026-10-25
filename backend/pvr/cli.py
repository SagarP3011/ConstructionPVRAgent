"""Command line interface: `python -m pvr.cli <command>`.

Commands:
    check-llm   Confirm the OpenAI key works and OPENAI_MODEL supports tool calling.
    engines     Deterministic assessment for the three default changes (no LLM).
    agent       Run one agent alone, live (for example: agent cost --change wall_height).
    run         Full multi-agent run in the console, with an approval prompt.
    save-fixture  Save a completed, approved run as a replay fixture.
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

    from pvr.models import Overrides

    data = get_data()
    if args.change:
        runs = [(args.change, _parse_params(args.param), args.mode)]
    else:
        # Defaults: the wall in contractor PVR mode (it has a claim to check), the others as what-ifs.
        runs = [(ct.id, {}, ct.modes[0]) for ct in data.scenario.change_types]
    overrides = Overrides(cost_contingency_remaining_aed=args.contingency, time_buffer_working_days=args.time_buffer)
    try:
        reports = [assessment_report(make_context(data, ct, params, mode=mode, overrides=overrides), data)
                   for ct, params, mode in runs]
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


def _ask(prompt: str, default: str = "") -> str:
    answer = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return answer or default


def cmd_run(args: argparse.Namespace) -> int:
    """Full multi-agent run in the console. Pauses for approval, then executes the approved actions."""
    from pvr.console import ConsoleView
    from pvr.data_loader import get_data
    from pvr.engines import options as options_engine
    from pvr.engines.change import make_context
    from pvr.engines.common import EngineError
    from pvr.llm.client import LLMError, OpenAILLM
    from pvr.orchestrator.approvals import ApprovalError
    from pvr.orchestrator.orchestrator import RunAborted, start_run
    from pvr.report import aed, day

    settings = load_settings()
    data = get_data()
    try:
        mode = args.mode or data.change_type(args.change).modes[0]
        ctx = make_context(data, args.change, _parse_params(args.param), mode=mode)
        llm = OpenAILLM(settings)
    except (EngineError, KeyError, LLMError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(f"PVR Agent Room: {ctx.change_type} {ctx.parameters} ({ctx.mode}); "
          f"models {settings.openai_model} / {settings.light_model}")
    orch, sink = start_run(ctx, data, settings, llm, sinks=[ConsoleView(show_tools=not args.quiet)])
    try:
        request = orch.run_until_approval()
        s = orch.session
        print("\n=== Decision needed ===")
        for i, option_id in enumerate(request["options"], 1):
            o = options_engine.evaluate_option(s.ctx, s.data, options_engine.parse_option_id(option_id, s.data))
            backers = [a for a, st in request["stances"].items() if st == option_id]
            print(f"  {i}. {option_id}: delay {o.delay_working_days} wd, completion {day(o.completion_date)}, "
                  f"total AED {aed(o.total_cost_aed)}, buffer left {o.time_buffer_remaining_days} wd, "
                  f"contingency left AED {aed(o.contingency_remaining_aed)}"
                  + (f"  (supported by {', '.join(backers)})" if backers else ""))
        print("  Actions proposed:")
        for a in request["pending_actions"]:
            title = a["payload"].get("title") or ", ".join(a["payload"].get("recipients", []))
            print(f"    {a['action_id']} {a['type']}{f' ({title})' if title else ''}: {a['reason']}")

        if args.reject:
            orch.reject(args.approver or "Console user", args.role or "Reviewer", args.reject)
            print("Rejected. Nothing was executed.")
            return 0
        if args.approve:
            option, name, role = args.approve, args.approver, args.role
            actions = [a["action_id"] for a in request["pending_actions"]] if args.actions == "all" \
                else [x for x in (args.actions or "").split(",") if x]
        else:
            choice = _ask("Choose an option number, or r to reject", "1")
            name = _ask("Your name")
            role = _ask("Your role")
            if choice.lower() == "r":
                orch.reject(name, role, _ask("Reason for rejecting"))
                print("Rejected. Nothing was executed.")
                return 0
            option = request["options"][int(choice) - 1]
            all_ids = ",".join(a["action_id"] for a in request["pending_actions"])
            actions = [x.strip() for x in _ask("Actions to approve (comma separated)", all_ids).split(",") if x.strip()]
        executed = orch.approve(option, actions, name or "", role or "")
        print(f"\nApproved {option} by {name} ({role}). Executed {len(executed)} action(s).")
        print(f"Outputs: {s.run_dir / 'outputs'}")
    except RunAborted as exc:
        print(f"Run stopped: {exc}", file=sys.stderr)
        return 1
    except (ApprovalError, ValueError, IndexError) as exc:
        print(f"Approval error: {exc}", file=sys.stderr)
        return 1
    finally:
        sink.close()
        usage = [e.payload for e in orch.session.bus.of_type("llm.call")]
        print(f"LLM calls {len(usage)}; tokens {sum(u['prompt_tokens'] for u in usage)} in / "
              f"{sum(u['completion_tokens'] for u in usage)} out")
        print(f"Trace: {sink.path}")
    return 0


def cmd_save_fixture(args: argparse.Namespace) -> int:
    """Copy a completed, approved run to fixtures/demo_run_<change_type>.jsonl for offline replay."""
    from pvr.events.snapshot import run_snapshot
    from pvr.events.store import read_events, save_fixture

    try:
        target = save_fixture(args.run_id, name=args.name)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    snap = run_snapshot(read_events(target))
    print(f"Saved {args.run_id} as {target.name}: {snap.context.get('change_type')} {snap.context.get('parameters')} "
          f"({snap.context.get('mode')}), {snap.event_count} events, debate {snap.debate.get('rounds')} round(s), "
          f"options {[o['option_id'] for o in snap.options]}, approved {(snap.decision or {}).get('option_id')}")
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
    engines.add_argument("--contingency", type=float, metavar="AED",
                         help="What-if: remaining cost contingency instead of the project's")
    engines.add_argument("--time-buffer", type=int, metavar="DAYS",
                         help="What-if: time buffer in working days instead of the project's")
    engines.set_defaults(func=cmd_engines)

    agent = sub.add_parser("agent", help="Run one agent alone, live, with earlier stages pre-filled from engines.")
    agent.add_argument("name", help="Agent name, for example cost")
    agent.add_argument("--change", required=True, help="Change type, for example wall_height")
    agent.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                       help="Parameter value, repeatable (defaults otherwise)")
    agent.add_argument("--mode", choices=["internal_what_if", "contractor_pvr"],
                       help="Mode (default: the first mode of the change type)")
    agent.set_defaults(func=cmd_agent)

    run = sub.add_parser("run", help="Full multi-agent run in the console, with an approval prompt.")
    run.add_argument("--change", required=True, help="Change type, for example wall_height")
    run.add_argument("--param", action="append", default=[], metavar="NAME=VALUE",
                     help="Parameter value, repeatable (defaults otherwise)")
    run.add_argument("--mode", choices=["internal_what_if", "contractor_pvr"],
                     help="Mode (default: the first mode of the change type)")
    run.add_argument("--approve", metavar="OPTION_ID", help="Approve this option without prompting")
    run.add_argument("--actions", default="all", help="With --approve: 'all' or comma-separated action ids")
    run.add_argument("--reject", metavar="REASON", help="Reject without prompting")
    run.add_argument("--approver", help="Approver name (with --approve or --reject)")
    run.add_argument("--role", help="Approver role (with --approve or --reject)")
    run.add_argument("--quiet", action="store_true", help="Do not print tool calls")
    run.set_defaults(func=cmd_run)

    fixture = sub.add_parser("save-fixture", help="Save a completed, approved run as the replay fixture for its "
                                                  "change type.")
    fixture.add_argument("run_id", help="Run id, for example R-20261025-101500-a1b2")
    fixture.add_argument("--name", help="Save as demo_run_<name> (for example wall_3m) instead of replacing the "
                                        "default demo run of the change type")
    fixture.set_defaults(func=cmd_save_fixture)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point."""
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
