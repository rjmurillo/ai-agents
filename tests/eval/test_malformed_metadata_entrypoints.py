"""One-call stop tests for eval entrypoints that recover ordinary failures."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import NoReturn

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = REPO_ROOT / "scripts" / "eval"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    original_sys_path = sys.path.copy()
    sys.path.insert(0, str(EVAL_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_sys_path
    return module


def _raise_metadata_error(error_type: type[RuntimeError]) -> NoReturn:
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
        stderr=json.dumps(
            {
                "level": "error",
                "event": "MalformedProviderMetadataError",
            }
        )
        + "\n",
    )
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: completed)
    tier = module.default_panel().tiers[0]

    with pytest.raises(module.MalformedProviderMetadataError):
        module._default_runner("qa", tier, 1, "fixtures")


def test_model_panel_does_not_accept_metadata_event_substrings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "model_panel_child_metadata_substring",
        EVAL_DIR / "eval-model-panel.py",
    )
    completed = subprocess.CompletedProcess(
        args=["child"],
        returncode=module.EXIT_EXTERNAL,
        stdout="",
        stderr="log mentions event=MalformedProviderMetadataError but is not JSON\n",
    )
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: completed)
    tier = module.default_panel().tiers[0]

    with pytest.raises(RuntimeError) as exc_info:
        module._default_runner("qa", tier, 1, "fixtures")

    assert not isinstance(exc_info.value, module.MalformedProviderMetadataError)


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


def test_agent_assessment_entrypoint_stops_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load("agent_assessment_metadata_stop", EVAL_DIR / "eval-agents.py")
    calls = 0

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(sys, "argv", ["eval-agents.py", "--dry-run"])
    monkeypatch.setattr(module, "list_agents", lambda: ["qa"])
    monkeypatch.setattr(module, "PROMPTS", {"qa": [{"prompt": "q"}]})
    monkeypatch.setattr(module, "run_assessment", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.main()

    assert calls == 1


def test_knowledge_eval_entrypoint_stops_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "knowledge_eval_metadata_stop",
        EVAL_DIR / "eval-knowledge-integration.py",
    )
    calls = 0

    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(sys, "argv", ["eval-knowledge-integration.py", "--dry-run"])
    monkeypatch.setattr(module, "SKILLS", ["skill"])
    monkeypatch.setattr(module, "PROMPTS", {"skill": [{"prompt": "q"}]})
    monkeypatch.setattr(module, "run_assessment", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.main()

    assert calls == 1


def test_prompt_change_entrypoint_stops_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "prompt_change_metadata_stop",
        EVAL_DIR / "eval-prompt-change.py",
    )
    calls = 0
    args = SimpleNamespace(
        provider=None,
        scenarios="scenarios.json",
        runs=1,
        security_critical=False,
        model="model",
        dry_run=False,
    )

    def fail(*values: object) -> None:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "_parse_args", lambda: args)
    monkeypatch.setattr(module, "load_scenarios", lambda path: [{}])
    monkeypatch.setattr(module, "_load_prompts", lambda parsed: ("before", "after", "test"))
    monkeypatch.setattr(module, "load_api_key_for_selected_provider", lambda provider: "")
    monkeypatch.setattr(module, "verify_model_available", lambda key, model: None)
    monkeypatch.setattr(module, "_run_and_report", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.main()

    assert calls == 1


def test_reviewer_asymmetry_entrypoint_stops_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load(
        "reviewer_asymmetry_metadata_stop",
        EVAL_DIR / "eval-reviewer-asymmetry.py",
    )
    calls = 0
    args = SimpleNamespace(
        fixtures=str(tmp_path),
        trials=1,
        model="model",
        base_ref="base",
        output=None,
        dry_run=False,
    )

    def fail(*values: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "load_fixtures", lambda path: [{"agent": "qa"}])
    monkeypatch.setattr(module, "TEMPLATES", {"qa": "qa.md"})
    monkeypatch.setattr(
        module,
        "load_template",
        lambda path, ref: "control" if ref else "treatment",
    )
    monkeypatch.setattr(module, "load_api_key_for_selected_provider", lambda: "")
    monkeypatch.setattr(module, "run_eval", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.main()

    assert calls == 1


def test_skill_overlap_entrypoint_stops_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "skill_overlap_metadata_stop",
        EVAL_DIR / "eval-skill-overlap.py",
    )
    calls = 0
    config = module.PairsConfig(
        pairs=[("a", "b")],
        prompts={"a": [], "b": []},
    )
    args = SimpleNamespace(
        pairs="pairs.json",
        run_id=None,
        model=module.DEFAULT_MODEL,
        dry_run=False,
    )

    def fail(*values: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "load_pairs_file", lambda path: config)
    monkeypatch.setattr(module, "_validate_pair_skill_dirs", lambda pairs, root: None)
    monkeypatch.setattr(module, "_load_api_key_for_selected_provider", lambda: "")
    monkeypatch.setattr(module, "make_response_fn", lambda key, model: fail)
    monkeypatch.setattr(module, "make_judge_fn", lambda key, model: fail)
    monkeypatch.setattr(module, "evaluate_pair", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.run(args)

    assert calls == 1


def test_skill_router_call_boundary_preserves_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "skill_router_call_metadata_stop",
        EVAL_DIR / "eval_skill_router.py",
    )
    calls = 0

    def fail(*values: object, **kwargs: object) -> str:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "call_api", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.call_router("key", "prompt")

    assert calls == 1


def test_skill_router_entrypoint_stops_after_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load(
        "skill_router_metadata_stop",
        EVAL_DIR / "eval_skill_router.py",
    )
    calls = 0
    args = SimpleNamespace(
        fixtures="fixtures.json",
        repo_root=".",
        limit=None,
        dry_run=False,
    )
    plan = [{"fixture": {"candidates": ["a"]}}]

    def fail(*values: object, **kwargs: object) -> dict[str, object]:
        nonlocal calls
        calls += 1
        _raise_metadata_error(module.MalformedProviderMetadataError)

    monkeypatch.setattr(module, "_parse_args", lambda: args)
    monkeypatch.setattr(module, "load_fixtures", lambda path: [{"id": "f"}])
    monkeypatch.setattr(module, "build_plan", lambda fixtures, root: plan)
    monkeypatch.setattr(module, "check_identical_arms", lambda items: [])
    monkeypatch.setattr(module, "load_api_key_for_selected_provider", lambda: "")
    monkeypatch.setattr(module, "run_eval", fail)

    with pytest.raises(module.MalformedProviderMetadataError):
        module.main()

    assert calls == 1
