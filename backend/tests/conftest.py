"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from pvr.config import Settings
from pvr.data_loader import get_data
from pvr.engines.change import make_context
from pvr.models import ProjectData
from pvr.orchestrator.context import RunSession
from pvr.orchestrator.single_agent import new_session


def fake_settings(**overrides: object) -> Settings:
    values: dict[str, object] = dict(
        openai_api_key="", openai_model="fake-model", openai_model_light="fake-light",
        llm_temperature=0.4, max_debate_rounds=3, agent_max_steps=8,
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def data() -> ProjectData:
    return get_data()


def make_session(change_type: str, params: dict | None = None, mode: str = "internal_what_if",
                 runs_dir: Path | None = None, **settings: object) -> RunSession:
    data = get_data()
    ctx = make_context(data, change_type, params, mode=mode)  # type: ignore[arg-type]
    session, _ = new_session(ctx, data, fake_settings(**settings), runs_dir=runs_dir)
    return session
