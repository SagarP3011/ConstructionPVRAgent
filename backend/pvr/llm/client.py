"""LLM client: a small interface, plus the OpenAI implementation (timeouts, 2 retries with backoff).

The API key is held by the OpenAI SDK client only; it is never logged. Each call returns token
counts and latency, which the agent runtime writes to the trace.
"""

from __future__ import annotations

import time
from typing import Any, Protocol

from pydantic import BaseModel, Field

from pvr.config import Settings


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: str


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    attempts: int = 1


class LLMError(RuntimeError):
    """The model call failed after retries. The message never contains the API key."""


class LLM(Protocol):
    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResponse: ...


class OpenAILLM:
    """Chat Completions with tool calling."""

    RETRIES = 2

    def __init__(self, settings: Settings, timeout_s: float = 90.0) -> None:
        from openai import OpenAI

        if not settings.has_api_key:
            raise LLMError("OPENAI_API_KEY is not set in .env")
        self._secret = settings.openai_api_key
        self._client = OpenAI(api_key=settings.openai_api_key, timeout=timeout_s, max_retries=0)
        self._no_temperature: set[str] = set()

    def _scrub(self, text: str) -> str:
        return text.replace(self._secret, "***")

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResponse:
        import openai

        retryable = (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError,
                     openai.RateLimitError)
        start = time.perf_counter()
        attempt = 0
        while True:
            attempt += 1
            kwargs: dict[str, Any] = {"model": model, "messages": messages}
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = tool_choice
            if temperature is not None and model not in self._no_temperature:
                kwargs["temperature"] = temperature
            try:
                response = self._client.chat.completions.create(**kwargs)
                break
            except openai.BadRequestError as exc:
                # Some models accept only their default temperature: retry once without it.
                if "temperature" in str(exc) and model not in self._no_temperature:
                    self._no_temperature.add(model)
                    attempt -= 1
                    continue
                raise LLMError(self._scrub(f"Model request rejected: {exc}")) from None
            except retryable as exc:
                quota = getattr(exc, "code", None) == "insufficient_quota" or "insufficient_quota" in str(exc)
                if quota or attempt > self.RETRIES:
                    raise LLMError(self._scrub(f"{type(exc).__name__}: {exc}")) from None
                time.sleep(2.0 * 2 ** (attempt - 1))
            except openai.OpenAIError as exc:
                raise LLMError(self._scrub(f"{type(exc).__name__}: {exc}")) from None

        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            content=choice.message.content,
            tool_calls=[
                ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "")
                for tc in (choice.message.tool_calls or []) if tc.type == "function"
            ],
            finish_reason=choice.finish_reason,
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            latency_ms=int((time.perf_counter() - start) * 1000),
            attempts=attempt,
        )
