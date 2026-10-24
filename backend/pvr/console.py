"""Console view of a run: a readable line for each important event (used by `cli.py run`)."""

from __future__ import annotations

import textwrap

from pvr.models import Event

_SHOWN_TOOLS_ARGS = {"search_contract", "search_boq", "get_clause", "get_boq_item", "evaluate_option",
                     "check_buffer", "run_cpm", "check_notice"}


def _wrap(text: str, indent: str = "      ") -> str:
    return textwrap.fill(text, width=110, initial_indent=indent, subsequent_indent=indent)


class ConsoleView:
    """Event sink that prints the run as it happens."""

    def __init__(self, show_tools: bool = True) -> None:
        self.show_tools = show_tools

    def __call__(self, event: Event) -> None:
        p = event.payload
        t = event.type
        if t == "stage.started":
            print(f"\n=== Stage: {p['stage']} ===")
        elif t == "stage.completed" and p.get("stage") == "debate":
            print(f"    (debate ended after {p['rounds']} round(s): {p['stop_reason'].replace('_', ' ')})")
        elif t == "agent.active" and p.get("answer_turn"):
            pass
        elif t == "tool.called" and self.show_tools and p["agent"] != "orchestrator" \
                and p["tool"] not in ("post_message", "ask_agent", "read_blackboard"):
            args = ", ".join(f"{k}={v!r}" for k, v in p["args"].items()) if p["tool"] in _SHOWN_TOOLS_ARGS else ""
            print(f"    . {p['agent']} called {p['tool']}({args})")
        elif t == "tool.result" and not p["ok"] and p["agent"] != "orchestrator":
            print(f"    ! {p['agent']} {p['tool']} error: {p['error']}")
        elif t == "ask.sent":
            print(f"    ? {p['from']} asks {p['to']}: {p['question']}")
        elif t == "message.posted" and p["intent"] != "ASK":
            stance = f" | stance {p['stance']}" if p.get("stance") else ""
            fix = f" | corrects {p['corrects']}" if p.get("corrects") else ""
            print(f"  {p['message_id']} {p['from']} -> {p['to']} [{p['intent']}]{stance}{fix}")
            print(_wrap(p["content"]))
        elif t == "verification.result":
            if p["status"] == "pass":
                print(f"      verified: {p['claims_checked']} claim(s) ok")
            else:
                label = "UNRESOLVED" if p["unresolved"] else "FAILED"
                print(f"      verification {label}:")
                for issue in p["issues"]:
                    print(_wrap(f"- {issue}", "        "))
        elif t == "message.corrected":
            print(f"    ~ {p['original_message_id']} replaced by {p['corrected_message_id']}")
        elif t == "stance.changed":
            print(f"    * {p['agent']} stance: {p['from'] or 'none'} -> {p['to']}")
        elif t == "action.proposed":
            print(f"    + {p['proposed_by']} proposed {p['action_id']} {p['type']}: {p['reason']}")
        elif t == "action.executed":
            print(f"    executed {p['action_id']} {p['type']}: {', '.join(p['files'])}")
        elif t == "run.error":
            print(f"    ERROR {p.get('agent', '')}: {p['error']}")
