"""Stage names and the generic instruction each agent receives for a stage (SPEC 10.2).

Instructions say what the stage is for and how to end the turn. They never list tool calls, and
they are the same for every change type.
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
        "as you see fit. Where a conclusion of yours depends on another agent's area (for example what the "
        "contract allows, or what the programme shows), ask that agent rather than assume. When you are "
        "done, post one ASSESS message to all."
    ),
    "commercial": (
        "Stage: commercial check. The assessments from the other agents are below. Find the full set of "
        "options for this change and judge them against the time buffer and the cost contingency. "
        "When you are done, post one ASSESS message to all, with your stance."
    ),
    "synthesis": (
        "Stage: synthesis. The assessment and the debate are below, with each agent's final stance on the "
        "blackboard. Prepare the decision for the person who will approve it. Propose every action they "
        "should be able to approve, including a task for each open issue you report, and post one "
        "SUMMARISE message to all."
    ),
}


def stage_instruction(stage: str) -> str:
    """Instruction for a stage. Raises KeyError for a stage without one."""
    return STAGE_INSTRUCTIONS[stage]


def debate_instruction(round_: int, max_rounds: int, stances: dict[str, str | None], agent: str) -> str:
    """Instruction for one debater in one round."""
    current = ", ".join(f"{a}: {s or 'none yet'}" for a, s in stances.items())
    return (
        f"Stage: debate, round {round_} of at most {max_rounds}. Read the other agents' messages below and "
        "respond to one specific agent: PROPOSE an option, CHALLENGE a point you disagree with, or AGREE "
        "with them. Address your message to that agent (not to all) and give your stance: the option id you "
        f"now prefer. Current stances: {current}. Your own stance is {stances.get(agent) or 'not set yet'}. "
        "Keep it if you are still convinced; change it if another agent has given you a sound reason backed "
        "by facts. An option that another option beats on both total cost and delay is not a sensible "
        "stance. Mention only option ids evaluated in this run."
    )


def answer_instruction(asker: str, question: str) -> str:
    return (
        f"The {asker} agent asks you: \"{question}\" Answer briefly and precisely within your role, using "
        f"your tools if you need facts. Post one ANSWER message to {asker}."
    )


def verifier_instruction(author: str, message_id: str, issues: list[str]) -> str:
    listed = "\n".join(f"- {i}" for i in issues)
    return (
        f"Stage: verification. Code checked message {message_id} from the {author} agent against the facts of "
        f"this run and found these problems:\n{listed}\nPost one VERIFY message to {author} that explains them."
    )


def correction_instruction(message_id: str, issues: list[str]) -> str:
    listed = "\n".join(f"- {i}" for i in issues)
    return (
        f"Your message {message_id} failed verification. Problems:\n{listed}\n"
        "Post a corrected message: same addressee, same intent and the same substance, with every problem "
        "fixed. Use only numbers from tool results in this run, each cited with its fact id in square "
        "brackets straight after it, for example 'AED 1,234.50 [F-0012]'; the problems list the fact ids "
        "that hold each value. Call tools again if you need a fact. If a number or claim has no fact that "
        "supports it (for example a "
        "difference or count you worked out yourself), remove it from the text and from the claims. This is "
        "your only chance to correct it."
    )
