"""Approval gate: nothing executes until a named person approves (SPEC 10.5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pvr.ids import now_iso
from pvr.orchestrator.context import RunSession


class ApprovalError(RuntimeError):
    """Raised for an invalid approval, or for any attempt to execute without one."""


class Decision(BaseModel):
    status: Literal["approved", "rejected"]
    option_id: str | None = None
    approved_action_ids: list[str] = Field(default_factory=list)
    approver_name: str
    approver_role: str
    reason: str = ""
    timestamp: str


def make_approval(
    session: RunSession,
    presented_option_ids: list[str],
    option_id: str,
    action_ids: list[str],
    approver_name: str,
    approver_role: str,
) -> Decision:
    """Validate an approval: a presented option, known pending actions, a named approver with a role."""
    if not approver_name.strip() or not approver_role.strip():
        raise ApprovalError("The approver's name and role are required")
    if option_id not in presented_option_ids:
        raise ApprovalError(f"Option {option_id} was not presented. Choose one of: {', '.join(presented_option_ids)}")
    pending = {a.action_id for a in session.pending_actions if a.status == "pending"}
    unknown = [a for a in action_ids if a not in pending]
    if unknown:
        raise ApprovalError(f"Unknown or not pending action(s): {', '.join(unknown)}")
    return Decision(status="approved", option_id=option_id, approved_action_ids=list(dict.fromkeys(action_ids)),
                    approver_name=approver_name.strip(), approver_role=approver_role.strip(), timestamp=now_iso())


def make_rejection(approver_name: str, approver_role: str, reason: str) -> Decision:
    if not approver_name.strip() or not approver_role.strip():
        raise ApprovalError("The approver's name and role are required")
    if not reason.strip():
        raise ApprovalError("A reason is required to reject")
    return Decision(status="rejected", approver_name=approver_name.strip(), approver_role=approver_role.strip(),
                    reason=reason.strip(), timestamp=now_iso())
