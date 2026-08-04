"""One-call stop tests for eval entrypoints that recover ordinary failures."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    original_sys_path = sys.path.copy()
    sys.path.insert(0, str(EVAL_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path
    return module


def _raise_metadata_error(error_type: type[RuntimeError]) -> None:
    raise error_type("malformed provider metadata")


def test_generation_eval_stops_after_one_malformed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "generation_eval_metadata_stop",
        REPO_ROOT / "evals/spec-generator-spike/run_generation_eval.py",
    )
    calls = 0

    def fail(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "call_api", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.run_prompt("key", "system", module.FEATURES[0], runs=3)

    assert calls == 1


def test_oneshot_eval_stops_after_one_malformed_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "oneshot_eval_metadata_stop",
        EVAL_DIR / "eval-oneshot-vs-shipped.py",
    )
    fixture = module.Fixture(
        id="f1",
        source_repo="owner/repo",
        issue_number=1,
        title="title",
        discourse="discourse",
        shipped_fix="fix",
    )
    calls = 0

    def fail(*args: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "_call_api", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.grade_fixture(fixture, api_key="key", model="model")

    assert calls == 1


def test_model_panel_stops_after_one_malformed_cell() -> None:
    module = _load(
        "model_panel_metadata_stop",
        EVAL_DIR / "eval-model-panel.py",
    )
    calls = 0

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.sweep(
            module.default_panel(),
            ["qa", "security"],
            fixtures_template="evals/{unit}-spike/fixtures",
            n_runs=3,
            runner=fail,
        )

    assert calls == 1


def test_model_panel_recovers_typed_failure_from_child_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "model_panel_child_metadata_stop",
        EVAL_DIR / "eval-model-panel.py",
    )
    completed = subprocess.CompletedProcess(
        args=["child"],
        returncode=module.EXIT_EXTERNAL,
        stdout="",
        stderr="event=MalformedProviderMetadataError\n",
    )
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: completed)
    tier = module.default_panel().tiers[0]

    with pytest.raises(module.MalformedProviderMetadataError):
        module._default_runner("qa", tier, 1, "fixtures")


def test_agent_harness_emits_dedicated_child_marker_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load(
        "agent_eval_metadata_stop",
        EVAL_DIR / "eval-agent-vs-baseline.py",
    )
    calls = 0

    def fail(**kwargs: object) -> int:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "_run_live", fail)
    code = module._run_live_with_metadata_exit(
        args=object(),
        fixtures=[],
        fixture_paths=[],
        plan=object(),
    )

    assert code == module.EXIT_EXTERNAL
    assert calls == 1
    assert "MalformedProviderMetadataError" in capsys.readouterr().err
