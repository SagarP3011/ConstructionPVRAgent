"""Phase 0 scaffold tests: health endpoint, repository paths, settings, check-llm safety."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pvr.api.main import app
from pvr.config import DATA_DIR, GOLDEN_PATH, REPO_ROOT, Settings, load_settings
from pvr.llm.check import LlmCheckResult, ModelCheck, _describe_error, check_llm


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
        openai_api_key="",
        openai_model="",
        openai_model_light="",
        llm_temperature=0.4,
        max_debate_rounds=3,
        agent_max_steps=8,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_health_returns_ok() -> None:
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data_dir_found"] is True
    assert body["golden_found"] is True


def test_data_is_read_from_repository_root() -> None:
    assert (REPO_ROOT / "SPEC.md").is_file()
    assert DATA_DIR == REPO_ROOT / "data"
    assert GOLDEN_PATH == REPO_ROOT / "tests_golden" / "golden.json"
    expected = {"boq", "commercial", "contract", "documents", "productivity", "project", "scenario", "schedule"}
    assert expected <= {p.stem for p in DATA_DIR.glob("*.json")}
    # Data must not be copied into the backend.
    assert not (Path(__file__).resolve().parents[1] / "data").exists()


def test_settings_defaults_when_env_empty(tmp_path: Path, monkeypatch) -> None:
    for name in ("OPENAI_API_KEY", "OPENAI_MODEL", "OPENAI_MODEL_LIGHT", "LLM_TEMPERATURE",
                 "MAX_DEBATE_ROUNDS", "AGENT_MAX_STEPS"):
        monkeypatch.delenv(name, raising=False)
    settings = load_settings(tmp_path / "missing.env")
    assert settings.llm_temperature == 0.4
    assert settings.max_debate_rounds == 3
    assert settings.agent_max_steps == 8
    assert settings.has_api_key is False


def test_settings_repr_hides_key() -> None:
    secret = "sk-test-secret-value"
    assert secret not in repr(_settings(openai_api_key=secret))


def test_light_model_falls_back_to_main_model() -> None:
    assert _settings(openai_model="m-main").light_model == "m-main"
    assert _settings(openai_model="m-main", openai_model_light="m-light").light_model == "m-light"


def test_check_llm_without_key_makes_no_call() -> None:
    result = check_llm(_settings())
    assert result.key_configured is False
    assert result.ok is False


def test_error_text_never_contains_key() -> None:
    secret = "sk-test-secret-value"
    text = _describe_error(RuntimeError(f"bad key {secret}"), secret)
    assert secret not in text


def test_check_result_ok_requires_tool_calling() -> None:
    good = ModelCheck(model="m", available=True, supports_tool_calling=True)
    bad = ModelCheck(model="m", available=True, supports_tool_calling=False)
    assert LlmCheckResult(key_configured=True, key_works=True, models=[good]).ok
    assert not LlmCheckResult(key_configured=True, key_works=True, models=[good, bad]).ok
    assert not LlmCheckResult(key_configured=True, key_works=True, models=[]).ok
