"""Free-text change input (SPEC 16, Phase 7): the Intake agent reads a typed request and maps it to one of
the supported change types and its parameters, or declines it. The person confirms before any run.

The agent only picks the change type and copies sizes from the text (or a relative increase). Code
resolves and validates the parameters, fills the instruction text and checks that the agent's reading
contains no numbers, so every number the person sees comes from the request or from the engines.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from pvr.agents.base import _assistant_message
from pvr.agents.roster import PROMPTS_DIR
from pvr.config import Settings
from pvr.engines import change
from pvr.engines.common import EngineError
from pvr.llm.client import LLM, LLMError
from pvr.models import Mode, ProjectData, RunContext
from pvr.tools.registry import clean_schema

MAX_STEPS = 4
MAX_TEXT = 500
_DIGIT = re.compile(r"\d")


class ParameterChoice(BaseModel):
    name: str = Field(description="Parameter name, for example new_height_m")
    value: float | None = Field(default=None, description="The size as the person stated it")
    increase_by: float | None = Field(
        default=None, description="How much bigger than today's value, when the person says it relatively")


class ProposeArgs(BaseModel):
    change_type: str = Field(description="One of the supported change type ids")
    parameters: list[ParameterChoice] = Field(default_factory=list,
                                              description="Only the parameters the person mentioned")
    mode: Mode | None = Field(default=None, description="One of the change type's allowed modes, or null")
    reading: str = Field(description="One short sentence, without numbers, saying how you read the request")


class DeclineArgs(BaseModel):
    reason: str = Field(description="Why this cannot be assessed here, briefly and politely")


TOOLS: dict[str, tuple[type[BaseModel], str]] = {
    "propose_interpretation": (ProposeArgs, "Propose the change type, sizes and mode you read in the request."),
    "decline_request": (DeclineArgs, "Decline a request that is not one of the supported change types."),
}


class Interpretation(BaseModel):
    status: Literal["interpreted", "declined"]
    change_type: str | None = None
    title: str | None = None
    parameters: dict[str, float] = Field(default_factory=dict)
    mode: Mode | None = None
    instruction_text: str | None = None
    reading: str = ""
    reason: str = ""
    model: str = ""
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0


class InterpretError(RuntimeError):
    """The request could not be read (empty, too long, or the model did not finish)."""


def _schemas() -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": name, "description": description,
                                              "parameters": clean_schema(model.model_json_schema())}}
            for name, (model, description) in TOOLS.items()]


def change_types_brief(data: ProjectData) -> str:
    """The supported change types as the agent sees them (from scenario.json)."""
    lines = []
    for ct in change.list_change_types(data):
        lines.append(f"- `{ct.id}`: {ct.title} (element: {ct.element}). Allowed modes: {', '.join(ct.modes)}"
                     + ("; contractor_pvr only at the default sizes." if "contractor_pvr" in ct.modes else "."))
        for p in ct.parameters:
            today = ct.fixed.get(change.current_value_key(p.name))
            lines.append(f"  - `{p.name}`: {p.label}, from {p.min:g} to {p.max:g} in steps of {p.step:g}, "
                         f"default {p.default:g}" + (f"; today's value {today:g}" if today is not None else ""))
    return "\n".join(lines)


def _propose(args: ProposeArgs, data: ProjectData) -> tuple[Interpretation | None, str]:
    """Resolve and validate a proposal. Returns (result, "") or (None, error for the agent)."""
    try:
        ct = data.change_type(args.change_type)
    except KeyError:
        known = ", ".join(c.id for c in data.scenario.change_types)
        return None, f"Unknown change type {args.change_type}. Use one of: {known}, or decline the request."
    if _DIGIT.search(args.reading):
        return None, "The reading must not contain numbers; the sizes are shown separately. Rewrite it."
    try:
        values = {p.name: change.resolve_parameter(ct, p.name, p.value, p.increase_by) for p in args.parameters}
        modes = [args.mode] if args.mode else list(ct.modes)
        ctx: RunContext | None = None
        last_error: EngineError | None = None
        for mode in modes:  # without a stated mode, the first allowed mode that fits these sizes
            try:
                ctx = change.make_context(data, ct.id, values, mode=mode)
                break
            except EngineError as exc:
                last_error = exc
        if ctx is None:
            raise last_error or EngineError("No allowed mode fits this request")
        request_text = change.get_change_request(ctx, data).instruction_text
    except EngineError as exc:
        return None, f"{exc}. If the person asked for a size outside the allowed range, decline the request."
    return Interpretation(status="interpreted", change_type=ct.id, title=ct.title, parameters=dict(ctx.parameters),
                          mode=ctx.mode, instruction_text=request_text, reading=args.reading.strip()), ""


def interpret_request(text: str, data: ProjectData, settings: Settings, llm: LLM) -> Interpretation:
    """Read a typed request with the Intake agent. Raises InterpretError or LLMError."""
    request = text.strip()
    if not request:
        raise InterpretError("Type the change you want assessed")
    if len(request) > MAX_TEXT:
        raise InterpretError(f"Keep the request under {MAX_TEXT} characters")
    model = settings.light_model
    if not model:
        raise LLMError("OPENAI_MODEL is not set in .env")

    system = "Agent id: intake\n\n" + (PROMPTS_DIR / "intake_interpret.md").read_text(encoding="utf-8")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": "## Supported change types\n\n" + change_types_brief(data)
         + "\n\n## The person's request\n\n<request>\n" + request + "\n</request>"},
    ]
    usage = {"steps": 0, "prompt_tokens": 0, "completion_tokens": 0, "model": model}
    for _ in range(MAX_STEPS):
        resp = llm.complete(model=model, messages=messages, tools=_schemas(), temperature=settings.llm_temperature,
                            tool_choice="required")
        usage["steps"] += 1  # type: ignore[operator]
        usage["prompt_tokens"] += resp.prompt_tokens  # type: ignore[operator]
        usage["completion_tokens"] += resp.completion_tokens  # type: ignore[operator]
        usage["model"] = resp.model or model
        messages.append(_assistant_message(resp))
        if not resp.tool_calls:
            messages.append({"role": "user", "content": "End with propose_interpretation or decline_request."})
            continue
        for tc in resp.tool_calls:
            spec = TOOLS.get(tc.name)
            error = "" if spec else f"Unknown tool {tc.name}"
            result: Interpretation | None = None
            if spec:
                try:
                    args = spec[0].model_validate(json.loads(tc.arguments or "{}"))
                except (ValidationError, json.JSONDecodeError) as exc:
                    error = f"Invalid arguments: {exc}"
                else:
                    if isinstance(args, DeclineArgs):
                        result = Interpretation(status="declined", reason=args.reason.strip())
                    else:
                        result, error = _propose(args, data)  # type: ignore[arg-type]
            if result is not None:
                return result.model_copy(update=usage)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps({"error": error})})
    raise InterpretError("The request could not be read. Try saying it differently, or choose a change above.")
