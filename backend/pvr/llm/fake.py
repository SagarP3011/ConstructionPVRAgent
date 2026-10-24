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


AgentStep = LLMResponse | Callable[[list[dict[str, Any]]], LLMResponse]


class RoutedFakeLLM:
    """Scripted responses per agent (read from the `Agent id:` line of the system prompt).

    `scripts[agent]` is a list of steps used in order; `fallback(agent, messages)` answers when an
    agent's list is empty (or the agent has none).
    """

    def __init__(self, scripts: dict[str, list[AgentStep]],
                 fallback: Callable[[str, list[dict[str, Any]]], LLMResponse] | None = None) -> None:
        import threading

        self.scripts = {k: list(v) for k, v in scripts.items()}
        self.fallback = fallback
        self.requests: list[tuple[str, FakeRequest]] = []
        self._lock = threading.Lock()

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float | None,
        tool_choice: str | dict[str, Any] = "auto",
    ) -> LLMResponse:
        from pvr.agents.base import agent_of_prompt

        agent = agent_of_prompt(messages)
        with self._lock:
            self.requests.append((agent, FakeRequest(
                model=model, messages=[dict(m) for m in messages],
                tool_names=[t["function"]["name"] for t in tools], tool_choice=tool_choice)))
            queue = self.scripts.get(agent, [])
            step = queue.pop(0) if queue else None
        if step is None:
            if self.fallback is None:
                raise AssertionError(f"No scripted response left for agent {agent}")
            response = self.fallback(agent, messages)
        else:
            response = step(messages) if callable(step) else step
        return response.model_copy(update={"model": model, "prompt_tokens": 100, "completion_tokens": 20})

    def calls_for(self, agent: str) -> list[FakeRequest]:
        return [r for a, r in self.requests if a == agent]


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
