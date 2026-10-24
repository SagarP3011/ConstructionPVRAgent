"""Connectivity check for the OpenAI API.

Confirms that the API key works (by listing models), that `OPENAI_MODEL` (and
`OPENAI_MODEL_LIGHT`, if set) is available, and that the model supports tool
calling (one tiny call that must return a tool call). The key is never printed;
it is also scrubbed from any error text before that text is returned.
"""

from __future__ import annotations

from pydantic import BaseModel

from pvr.config import Settings

_PING_TOOL = {
    "type": "function",
    "function": {
        "name": "ping",
        "description": "Reply to a connectivity check.",
        "parameters": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}


class ModelCheck(BaseModel):
    """Result of checking one model."""

    model: str
    available: bool
    supports_tool_calling: bool | None = None
    detail: str = ""


class LlmCheckResult(BaseModel):
    """Overall result of the LLM connectivity check."""

    key_configured: bool
    key_works: bool
    models_visible: int = 0
    models: list[ModelCheck] = []
    error: str = ""

    @property
    def ok(self) -> bool:
        """True when the key works and every configured model supports tool calling."""
        return (
            self.key_works
            and bool(self.models)
            and all(m.available and m.supports_tool_calling for m in self.models)
        )


def _scrub(text: str, secret: str) -> str:
    """Remove the secret from text, so error messages never leak the key."""
    return text.replace(secret, "***") if secret else text


def _describe_error(exc: Exception, secret: str) -> str:
    """Short, key-free description of an exception."""
    status = getattr(exc, "status_code", None)
    prefix = f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")
    return _scrub(f"{prefix}: {exc}", secret)[:300]


def _check_tool_calling(client: object, model: str) -> tuple[bool, str]:
    """Make one tiny chat completion that requires a tool call."""
    response = client.chat.completions.create(  # type: ignore[attr-defined]
        model=model,
        messages=[{"role": "user", "content": "Connectivity check. Call the ping tool with ok=true."}],
        tools=[_PING_TOOL],
        tool_choice="required",
        max_completion_tokens=1000,
    )
    choice = response.choices[0]
    tool_calls = choice.message.tool_calls or []
    if tool_calls and tool_calls[0].function.name == "ping":
        return True, "tool call returned"
    return False, f"no tool call returned (finish_reason={choice.finish_reason})"


def check_llm(settings: Settings) -> LlmCheckResult:
    """Run the connectivity check and return a structured result."""
    from openai import OpenAI

    key = settings.openai_api_key
    if not key:
        return LlmCheckResult(key_configured=False, key_works=False, error="OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=key, timeout=30.0, max_retries=1)
    try:
        visible = {m.id for m in client.models.list()}
    except Exception as exc:  # noqa: BLE001 - report any failure without the key
        return LlmCheckResult(key_configured=True, key_works=False, error=_describe_error(exc, key))

    result = LlmCheckResult(key_configured=True, key_works=True, models_visible=len(visible))
    if not settings.openai_model:
        result.error = "OPENAI_MODEL is not set in .env"
        return result

    wanted = [settings.openai_model]
    if settings.openai_model_light and settings.openai_model_light != settings.openai_model:
        wanted.append(settings.openai_model_light)

    for model in wanted:
        if model not in visible:
            result.models.append(ModelCheck(model=model, available=False, detail="not in the model list for this key"))
            continue
        supports: bool | None
        try:
            supports, detail = _check_tool_calling(client, model)
        except Exception as exc:  # noqa: BLE001 - the call failed, so tool support is unknown
            supports, detail = None, _describe_error(exc, key)
        result.models.append(ModelCheck(model=model, available=True, supports_tool_calling=supports, detail=detail))
    return result
