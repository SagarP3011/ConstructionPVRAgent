"""Agent runtime loop (SPEC 9).

Build messages (system prompt, stage instruction, relevant blackboard sections, messages addressed
to the agent), call the model with the agent's allowed tools, execute the tool calls the model
chooses, append the results, and repeat until the agent calls `post_message` or reaches the step
limit. On the limit, ask once for `post_message`, then mark the turn failed. Nothing here decides
which tools are called: the model does.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel

from pvr.agents.roster import PROMPTS_DIR, AgentSpec
from pvr.llm.client import LLM, LLMError, LLMResponse
from pvr.models import AgentMessage
from pvr.orchestrator.context import RunSession
from pvr.tools.registry import REGISTRY, ToolRegistry, ToolSpec

NUDGE_POST = "Please end your turn by calling post_message."
NUDGE_LIMIT = "You have reached the step limit. Call post_message now with what you have established."


class AgentTurn(BaseModel):
    agent: str
    status: Literal["posted", "failed"]
    message: AgentMessage | None = None
    steps: int
    forced: bool = False
    error: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


def system_prompt(spec: AgentSpec, tools: list[ToolSpec]) -> str:
    """Agent prompt plus the shared rules, with the allowed tools listed."""
    common = (PROMPTS_DIR / "_common.md").read_text(encoding="utf-8")
    own = spec.prompt_file.read_text(encoding="utf-8")
    tool_lines = "\n".join(f"- `{t.name}`: {t.description}" for t in tools)
    return own.strip() + "\n\n" + common.replace("{tools}", tool_lines).strip() + "\n"


def _format_inbox(messages: list[AgentMessage]) -> str:
    lines = []
    for m in messages:
        claims = "; ".join(f"{c.label} = {c.value} {c.unit} [{c.fact_id}]" for c in m.claims)
        lines.append(f"- {m.message_id} from {m.from_agent} to {m.to} ({m.intent}): {m.content}"
                     + (f"\n  Claims: {claims}" if claims else ""))
    return "\n".join(lines)


def build_context_message(
    session: RunSession,
    spec: AgentSpec,
    stage_instruction: str,
    blackboard_sections: list[str],
    inbox: list[AgentMessage],
    registry: ToolRegistry,
) -> str:
    """Stage instruction, blackboard sections (read through the tool, so their numbers get fact ids)
    and the messages addressed to this agent."""
    parts = [f"## Stage\n\n{stage_instruction}"]
    sections = []
    for section in blackboard_sections:
        if session.blackboard.read(section) is None:
            continue
        outcome = registry.dispatch(session, "read_blackboard", {"section": section}, agent="orchestrator")
        sections.append(f"### {section}\n\n```json\n{outcome.model_content}\n```")
    filled = ", ".join(session.blackboard.filled()) or "none"
    parts.append("## Shared blackboard\n\n" + ("\n\n".join(sections) if sections else "Nothing shown here.")
                 + f"\n\nSections with content: {filled}. Read others with read_blackboard if useful.")
    if inbox:
        parts.append("## Messages to you\n\n" + _format_inbox(inbox))
    return "\n\n".join(parts)


def _model_for(session: RunSession, spec: AgentSpec) -> str:
    s = session.settings
    return s.light_model if spec.model_tier == "light" else s.openai_model


def _assistant_message(resp: LLMResponse) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": resp.content}
    if resp.tool_calls:
        message["tool_calls"] = [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": tc.arguments}}
            for tc in resp.tool_calls
        ]
    return message


def run_agent_turn(
    session: RunSession,
    spec: AgentSpec,
    llm: LLM,
    stage_instruction: str,
    *,
    blackboard_sections: list[str] | None = None,
    inbox: list[AgentMessage] | None = None,
    registry: ToolRegistry = REGISTRY,
    max_steps: int | None = None,
) -> AgentTurn:
    """Run one turn of one agent until it posts a message, or fails."""
    tools = registry.available_for(session, list(spec.tools))
    tool_names = [t.name for t in tools]
    schemas = [t.openai_schema() for t in tools]
    limit = max_steps or session.settings.agent_max_steps
    model = _model_for(session, spec)
    session.bus.emit("agent.active", {
        "agent": spec.name, "stage": session.stage, "round": session.round, "model": model, "tools": tool_names,
        "unavailable_tools": [t for t in spec.tools if t not in tool_names],
    })

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt(spec, tools)},
        {"role": "user", "content": build_context_message(
            session, spec, stage_instruction, blackboard_sections or [], inbox or [], registry)},
    ]
    turn = AgentTurn(agent=spec.name, status="failed", steps=0)

    def finish(status: Literal["posted", "failed"], message: AgentMessage | None = None,
               forced: bool = False, error: str = "") -> AgentTurn:
        result = turn.model_copy(update={"status": status, "message": message, "forced": forced, "error": error})
        session.bus.emit("agent.idle", {
            "agent": spec.name, "status": status, "steps": result.steps, "forced": forced, "error": error,
            "message_id": message.message_id if message else None,
            "prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens,
        })
        return result

    def step(tool_choice: str | dict[str, Any]) -> AgentMessage | None:
        if not model:
            raise LLMError("OPENAI_MODEL is not set in .env")
        resp = llm.complete(model=model, messages=messages, tools=schemas,
                            temperature=session.settings.llm_temperature, tool_choice=tool_choice)
        turn.steps += 1
        turn.prompt_tokens += resp.prompt_tokens
        turn.completion_tokens += resp.completion_tokens
        session.bus.emit("llm.call", {
            "agent": spec.name, "model": resp.model or model, "step": turn.steps,
            "prompt_tokens": resp.prompt_tokens, "completion_tokens": resp.completion_tokens,
            "latency_ms": resp.latency_ms, "attempts": resp.attempts, "finish_reason": resp.finish_reason,
            "tool_calls": [tc.name for tc in resp.tool_calls], "content": resp.content,
        })
        messages.append(_assistant_message(resp))
        if not resp.tool_calls:
            messages.append({"role": "user", "content": NUDGE_POST})
            return None
        posted: AgentMessage | None = None
        for tc in resp.tool_calls:
            outcome = registry.dispatch(session, tc.name, tc.arguments, agent=spec.name, allowed=tool_names)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": outcome.model_content})
            if tc.name == "post_message" and outcome.ok and posted is None:
                posted = next(m for m in session.messages if m.message_id == outcome.result["message_id"])
        return posted

    try:
        for _ in range(limit):
            posted = step("auto")
            if posted:
                return finish("posted", posted)
        if messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": NUDGE_LIMIT})
        else:
            messages[-1] = {"role": "user", "content": NUDGE_LIMIT}
        posted = step({"type": "function", "function": {"name": "post_message"}})
        if posted:
            return finish("posted", posted, forced=True)
        return finish("failed", error=f"No post_message after {limit} steps and one reminder")
    except LLMError as exc:
        session.bus.emit("run.error", {"agent": spec.name, "error": str(exc)})
        return finish("failed", error=str(exc))


def message_json(message: AgentMessage) -> str:
    """Message envelope as JSON (with `from`)."""
    return json.dumps(message.model_dump(mode="json"), indent=2)
