"""Stage names and the generic instruction each agent receives for a stage (SPEC 10.2).

Instructions say what the stage is for and how to end the turn. They never list tool calls.
"""

from __future__ import annotations

STAGES: tuple[str, ...] = ("intake", "assessment", "commercial", "debate", "synthesis", "approval", "action")

STAGE_INSTRUCTIONS: dict[str, str] = {
    "intake": (
        "Stage: intake. Understand the change and package the evidence for the other agents. "
        "When you are done, post one ASSESS message to all."
    ),
    "assessment": (
        "Stage: assessment. Make your own assessment of this change within your role, using your tools "
        "as you see fit. When you are done, post one ASSESS message to all."
    ),
    "commercial": (
        "Stage: commercial check. Weigh the options against the time buffer and the cost contingency. "
        "When you are done, post one ASSESS message to all."
    ),
}


def stage_instruction(stage: str) -> str:
    """Instruction for a stage. Raises KeyError for a stage without one."""
    return STAGE_INSTRUCTIONS[stage]
