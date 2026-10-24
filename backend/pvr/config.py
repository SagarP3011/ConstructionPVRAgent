"""Configuration: repository paths, environment settings and model names.

Settings are read from the `.env` file at the repository root. The API key is
held in memory only; it is never printed or logged (`Settings.__repr__` hides it).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
DATA_DIR: Path = REPO_ROOT / "data"
GOLDEN_PATH: Path = REPO_ROOT / "tests_golden" / "golden.json"
RUNS_DIR: Path = REPO_ROOT / "runs"
FIXTURES_DIR: Path = REPO_ROOT / "fixtures"
ENV_PATH: Path = REPO_ROOT / ".env"


def _env_str(name: str, default: str = "") -> str:
    """Return an environment variable stripped of whitespace, or the default."""
    return (os.getenv(name) or default).strip()


def _env_float(name: str, default: float) -> float:
    """Return an environment variable as a float, or the default when empty."""
    raw = _env_str(name)
    return float(raw) if raw else default


def _env_int(name: str, default: int) -> int:
    """Return an environment variable as an int, or the default when empty."""
    raw = _env_str(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from the environment."""

    openai_api_key: str = field(repr=False)
    openai_model: str
    openai_model_light: str
    llm_temperature: float
    max_debate_rounds: int
    agent_max_steps: int

    @property
    def has_api_key(self) -> bool:
        """True when an API key is configured."""
        return bool(self.openai_api_key)

    @property
    def light_model(self) -> str:
        """Model for Intake and Verifier: the light model if set, else the main model."""
        return self.openai_model_light or self.openai_model


def load_settings(env_path: Path = ENV_PATH) -> Settings:
    """Load `.env` (without overriding variables already set) and build Settings."""
    load_dotenv(env_path, override=False)
    return Settings(
        openai_api_key=_env_str("OPENAI_API_KEY"),
        openai_model=_env_str("OPENAI_MODEL"),
        openai_model_light=_env_str("OPENAI_MODEL_LIGHT"),
        llm_temperature=_env_float("LLM_TEMPERATURE", 0.4),
        max_debate_rounds=_env_int("MAX_DEBATE_ROUNDS", 3),
        agent_max_steps=_env_int("AGENT_MAX_STEPS", 8),
    )
