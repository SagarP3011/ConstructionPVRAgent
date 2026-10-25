"""Action executor and artifact writers (SPEC 10.5).

Runs only after approval. Every number in an artifact comes from the engines (or from the
approved option, itself an engine result), never from agent text.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pvr.engines import buffer, change, cost, options, productivity, quantities
from pvr.engines.contract import get_clause
from pvr.ids import now_iso
from pvr.orchestrator.approvals import ApprovalError, Decision
from pvr.orchestrator.context import PendingAction, RunSession
from pvr.orchestrator.verifier import clause_refs
from pvr.tools.registry import to_jsonable


class ExecutedAction(BaseModel):
    action_id: str
    type: str
    files: list[str]
    executed_at: str


# --- content builders -------------------------------------------------------------------------


def cited_clauses(session: RunSession) -> list[dict[str, str]]:
    """Clauses referenced in the final (not superseded) messages, in contract order."""
    refs: set[str] = set()
    for m in session.messages:
        if m.superseded_by is None:
            refs.update(clause_refs(m.content))
    out = []
    for clause in session.data.contract.clauses:
        if clause.clause in refs:
            out.append({"clause": clause.clause, "title": clause.title})
    return out


def verification_summary(session: RunSession) -> dict[str, int]:
    checked = [m for m in session.messages if m.verification.status != "pending"]
    final = [m for m in checked if m.superseded_by is None]
    return {
        "messages_checked": len(checked),
        "final_messages_passed": sum(m.verification.status == "pass" for m in final),
        "final_messages_unresolved": sum(m.verification.status == "fail" for m in final),
        "messages_corrected": sum(m.superseded_by is not None for m in checked),
    }


def pvr_form(session: RunSession, decision: Decision, stances: dict[str, str | None],
             presented: list[str]) -> dict[str, Any]:
    ctx, data = session.ctx, session.data
    assert decision.option_id is not None
    impact = productivity.added_duration(ctx, data)
    chosen = options.evaluate_option(ctx, data, options.parse_option_id(decision.option_id, data))
    return {
        "form": "PVR output form",
        "run_id": session.run_id,
        "project": {"name": data.project.name, "contract_ref": data.project.contract_ref,
                    "contractor": data.project.contractor, "currency": data.project.currency},
        "change_request": to_jsonable(change.get_change_request(ctx, data)),
        "quantities": to_jsonable(quantities.quantify_change(ctx, data)),
        "cost": to_jsonable(cost.price_change(ctx, data)),
        "schedule_impact": {
            "activities": to_jsonable(impact.activities),
            "total_added_days": impact.total_added_days,
            "delay_without_acceleration_days": cost.no_acceleration_delay(ctx, data),
        },
        "chosen_option": to_jsonable(chosen),
        "chosen_option_buffer": to_jsonable(buffer.check_buffer(ctx, data, decision.option_id)),
        "presented_options": presented,
        "final_stances": stances,
        "clauses": cited_clauses(session),
        "approver": {"name": decision.approver_name, "role": decision.approver_role,
                     "approved_at": decision.timestamp},
        "verification": verification_summary(session),
    }


def verification_report(session: RunSession, decision: Decision) -> dict[str, Any]:
    ctx, data = session.ctx, session.data
    claim = cost.compare_contractor_claim(ctx, data)
    return {
        "report": "Verification of contractor claim",
        "run_id": session.run_id,
        "claim": to_jsonable(claim),
        "clauses": [{"clause": c, "title": get_clause(c, data).title}
                    for c in sorted({a.clause for a in claim.adjustments} | {claim.notice.clause})],
        "agent_message_verification": verification_summary(session),
        "approver": {"name": decision.approver_name, "role": decision.approver_role,
                     "approved_at": decision.timestamp},
    }


# --- HTML -----------------------------------------------------------------------------------------

_STYLE = """
body{font-family:Poppins,system-ui,sans-serif;color:#2C2A29;margin:32px;max-width:960px}
h1,h2{color:#003057;font-weight:600}h1{font-size:22px}h2{font-size:16px;margin-top:28px}
table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{border:1px solid #D7D2CB;padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#F7F6F4;font-weight:600;width:28%}td table th{width:auto}.note{color:#6E6A66;font-size:12px}
@page{size:A4;margin:14mm}
@media print{body{margin:0;max-width:none;font-size:11px}table{font-size:10px}h2{break-after:avoid}
tr{break-inside:avoid}th{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
"""


def _label(key: str) -> str:
    """A field name as a heading: "claimed_total_aed" -> "Claimed total AED"."""
    words = key.replace("_", " ").split()
    upper = {"aed", "pvr", "boq", "id", "eot", "cpm", "es", "ef", "ls", "lf", "tf"}
    text = " ".join(w.upper() if w.lower() in upper else w for w in words)
    return text[:1].upper() + text[1:]


def _cell(value: Any) -> str:
    if isinstance(value, dict):
        return _table(value)
    if isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            keys = list(dict.fromkeys(k for v in value for k in v))
            head = "".join(f"<th>{html.escape(_label(k))}</th>" for k in keys)
            rows = "".join("<tr>" + "".join(f"<td>{_cell(v.get(k, ''))}</td>" for k in keys) + "</tr>"
                           for v in value)
            return f"<table><tr>{head}</tr>{rows}</table>"
        return html.escape(", ".join(str(v) for v in value))
    return html.escape("" if value is None else str(value))


def _table(data: dict[str, Any]) -> str:
    rows = "".join(f"<tr><th>{html.escape(_label(k))}</th><td>{_cell(v)}</td></tr>" for k, v in data.items())
    return f"<table>{rows}</table>"


def render_html(title: str, content: dict[str, Any]) -> str:
    sections = "".join(f"<h2>{html.escape(_label(k))}</h2>{_cell(v)}"
                       for k, v in content.items() if isinstance(v, (dict, list)))
    header = _table({k: v for k, v in content.items() if not isinstance(v, (dict, list))})
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{_STYLE}</style></head><body><h1>{html.escape(title)}</h1>"
            "<p class='note'>Proof of concept by Sekuen, prepared for Aldar. Illustrative data.</p>"
            f"{header}{sections}</body></html>")


# --- executor --------------------------------------------------------------------------------------


def _write_json(path: Path, content: Any) -> None:
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")


def execute_actions(
    session: RunSession,
    decision: Decision | None,
    stances: dict[str, str | None],
    presented: list[str],
) -> list[ExecutedAction]:
    """Execute the approved actions and write artifacts under runs/<id>/outputs/.

    Raises ApprovalError (and emits run.error) when there is no approval.
    """
    if decision is None or decision.status != "approved":
        session.bus.emit("run.error", {"error": "Execution attempted before approval"})
        raise ApprovalError("Nothing can be executed before a person approves")
    if session.run_dir is None:
        raise ApprovalError("This run has no run folder to write outputs to")
    out_dir = session.run_dir / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    approved: list[PendingAction] = [a for a in session.pending_actions if a.action_id in decision.approved_action_ids]
    for action in session.pending_actions:
        action.status = "approved" if action in approved else "not_approved"

    executed: list[ExecutedAction] = []
    tasks: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []

    def done(action: PendingAction, files: list[str]) -> None:
        action.status = "executed"
        record = ExecutedAction(action_id=action.action_id, type=action.type, files=files, executed_at=now_iso())
        executed.append(record)
        session.bus.emit("action.executed", record.model_dump())

    for action in approved:
        if action.type == "draft_pvr_form":
            form = pvr_form(session, decision, stances, presented)
            _write_json(out_dir / "pvr_output_form.json", form)
            (out_dir / "pvr_output_form.html").write_text(render_html("PVR output form", form), encoding="utf-8")
            done(action, ["pvr_output_form.json", "pvr_output_form.html"])
        elif action.type == "draft_verification_report":
            report = verification_report(session, decision)
            _write_json(out_dir / "verification_report.json", report)
            (out_dir / "verification_report.html").write_text(
                render_html("Verification report", report), encoding="utf-8")
            done(action, ["verification_report.json", "verification_report.html"])
        elif action.type == "create_task":
            tasks.append({"task_id": action.action_id, "title": action.payload.get("title"),
                          "description": action.payload.get("description", ""),
                          "owner": action.payload.get("owner"), "reason": action.reason,
                          "proposed_by": action.proposed_by, "status": "open", "created_at": now_iso()})
            done(action, ["tasks.json"])
        elif action.type == "notify":
            notifications.append({"notification_id": action.action_id,
                                  "recipients": action.payload.get("recipients", []),
                                  "message": action.payload.get("message", ""), "reason": action.reason,
                                  "proposed_by": action.proposed_by, "sent_at": now_iso()})
            done(action, ["notifications.json"])

    if tasks:
        _write_json(out_dir / "tasks.json", tasks)
    if notifications:
        _write_json(out_dir / "notifications.json", notifications)
    _write_json(out_dir / "decision.json", {**decision.model_dump(), "presented_options": presented,
                                            "final_stances": stances,
                                            "executed": [e.model_dump() for e in executed]})
    session.blackboard.write("executed_actions", [e.model_dump() for e in executed], "action executor")
    return executed
