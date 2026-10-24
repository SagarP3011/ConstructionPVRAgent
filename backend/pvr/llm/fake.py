"""FakeLLM for tests: returns scripted responses in order and records every request."""

from __future__ import annotations

import json
from typing import Any, Callable

from pydantic import BaseModel

from pvr.llm.client import LLMResponse, ToolCall

Step = LLMResponse | Callable[[list[dict[str, Any]]], LLMResponse]


class FakeRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    tool_names: list[str]
    tool_choice: Any


class FakeLLM:
    """Each `complete` call takes the next step. A step is a response, or a function of the messages."""

    def __init__(self, steps: list[Step]) -> None:
        self._steps = list(steps)
        self.requests: list[FakeRequest] = []
        self._calls = 0

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResponse:
        self.requests.append(FakeRequest(
            model=model, messages=[dict(m) for m in messages],
            tool_names=[t["function"]["name"] for t in tools], tool_choice=tool_choice,
        ))
        if not self._steps:
            raise AssertionError("FakeLLM has no scripted response left")
        step = self._steps.pop(0)
        response = step(messages) if callable(step) else step
        return response.model_copy(update={"model": model, "prompt_tokens": 100, "completion_tokens": 20})

    @property
    def remaining(self) -> int:
        return len(self._steps)


def tool_call(name: str, args: dict[str, Any] | None = None, call_id: str | None = None) -> LLMResponse:
    """A response with one tool call."""
    return tool_calls([(name, args or {})], call_id)


def tool_calls(calls: list[tuple[str, dict[str, Any]]], call_id: str | None = None) -> LLMResponse:
    """A response with several tool calls."""
    base = call_id or "call"
    return LLMResponse(
        tool_calls=[ToolCall(id=f"{base}_{i}", name=n, arguments=json.dumps(a)) for i, (n, a) in enumerate(calls)],
        finish_reason="tool_calls",
    )


def text(content: str) -> LLMResponse:
    """A plain text response with no tool call."""
    return LLMResponse(content=content, finish_reason="stop")
